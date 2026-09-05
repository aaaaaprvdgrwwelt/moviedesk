"""Dateinamen zerlegen: Titel, Jahr, Staffel/Episode aus dem Rohnamen.

Kein Anspruch auf jeden Sonderfall - haeufige Szene-Konventionen reichen, der
Rest landet als unsicherer Treffer im Match-Dialog statt eine falsche
Automatik zu riskieren.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

#: Tags, die eine Freigabe ueblicherweise an den Titel haengt - alles ab dem
#: ersten Treffer gilt als Rauschen, nicht als Teil des Titels.
_NOISE = (
    "480p 576p 720p 1080p 2160p 4k uhd hdr "
    "bluray blu-ray webdl web-dl webrip web dvdrip brrip bdrip hdrip hdtv pdtv "
    "x264 x265 h264 h265 hevc avc xvid divx "
    "aac ac3 dts truehd atmos flac mp3 "
    "remux extended unrated directors.cut proper repack internal limited imax "
    "multi dual vostfr subbed dubbed retail "
).split()
_noise_re = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in _NOISE) + r")\b", re.IGNORECASE)

_year_re = re.compile(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)")

_SXXEYY = re.compile(r"[Ss](\d{1,2})[ .]?[Ee](\d{1,3})(?!\d)")
_NxNN = re.compile(r"(?<!\d)(\d{1,2})x(\d{2,3})(?!\d)")
_SEASON_WORD = re.compile(r"[Ss]eason[ ._-]*(\d{1,2})")
_EPISODE_WORD = re.compile(r"[Ee]pisode[ ._-]*(\d{1,3})")
_SEASON_ONLY = re.compile(r"\b[Ss](\d{1,2})\b")

VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".m4v", ".wmv", ".ts", ".webm", ".flv",
}

_SAMPLE_WORDS = ("sample", "trailer", "extra", "featurette")
_sample_re = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in _SAMPLE_WORDS) + r")\b", re.IGNORECASE)


def clean_words(text: str) -> str:
    text = text.replace(".", " ").replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", text).strip()


def _strip_noise(text: str) -> str:
    match = _noise_re.search(text)
    return text[:match.start()].strip() if match else text.strip()


def _strip_trailing_punct(text: str) -> str:
    return text.strip(" -._([")


@dataclass
class ParsedMovie:
    title: str
    year: int | None = None


@dataclass
class ParsedEpisode:
    series: str
    season: int
    episode: int
    year: int | None = None
    #: Titel-Text hinter der SxxEyy-Kennung im Dateinamen, falls vorhanden -
    #: Rueckfallebene fuer den Fall, dass die Quelle die Episode nicht kennt
    #: (z. B. ein Special, das TMDb anders/gar nicht katalogisiert hat).
    guessed_title: str = ""


def is_sample_or_extra(name: str) -> bool:
    # Ein erkennbares SxxEyy/NxNN im Namen macht das eindeutig zu einer
    # nummerierten Episode - dann ist "extra" o.ae. Teil des Episodentitels
    # (z. B. "Family Guy - S08E12 - Extra Large Medium"), kein Bonus-Feature.
    if _SXXEYY.search(name) or _NxNN.search(name):
        return False
    return bool(_sample_re.search(name))


def parse_movie(path: Path) -> ParsedMovie:
    """Titel/Jahr aus dem Dateinamen - der Ordnername hilft, falls die Datei
    selbst generisch heisst (z. B. `Film (2019)/movie.mkv`)."""
    stem = clean_words(path.stem)
    year_match = _year_re.search(stem)
    if year_match:
        title = _strip_trailing_punct(stem[:year_match.start()])
        return ParsedMovie(title=title, year=int(year_match.group(1)))

    # Kein Jahr im Dateinamen - haeufig heisst dann die Datei generisch
    # ("movie.mkv") und der Ordner traegt Titel und Jahr.
    folder = clean_words(path.parent.name)
    folder_year = _year_re.search(folder)
    if folder_year:
        title = _strip_trailing_punct(folder[:folder_year.start()])
        return ParsedMovie(title=title, year=int(folder_year.group(1)))

    title = _strip_trailing_punct(_strip_noise(stem))
    if not title or len(title) <= 2:
        title = _strip_trailing_punct(_strip_noise(folder)) or title
    return ParsedMovie(title=title, year=None)


def _season_episode(text: str) -> tuple[int, int] | None:
    match = _SXXEYY.search(text)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = _NxNN.search(text)
    if match:
        return int(match.group(1)), int(match.group(2))
    season_match = _SEASON_WORD.search(text)
    episode_match = _EPISODE_WORD.search(text)
    if season_match and episode_match:
        return int(season_match.group(1)), int(episode_match.group(1))
    return None


def parse_episode(path: Path) -> ParsedEpisode | None:
    """Serienname + Staffel/Episode. None, wenn kein Muster erkennbar ist.

    Sucht zuerst im Dateinamen; fehlt dort die Staffel (z. B. nur `E05.mkv`
    in einem `Season 01`-Ordner), wird der Ordner herangezogen.
    """
    stem = clean_words(path.stem)
    found = _season_episode(stem)
    series_source = stem
    marker_source = stem

    if found is None:
        season_match = _SEASON_ONLY.search(path.parent.name) or \
            _SEASON_WORD.search(path.parent.name)
        episode_match = _EPISODE_WORD.search(stem) or \
            re.search(r"\b[Ee](\d{1,3})\b", stem)
        if season_match and episode_match:
            found = (int(season_match.group(1)), int(episode_match.group(1)))
            series_source = clean_words(path.parent.parent.name)

    if found is None:
        return None

    season, episode = found
    marker = _SXXEYY.search(marker_source) or _NxNN.search(marker_source)
    guessed_title = _strip_trailing_punct(
        _strip_noise(marker_source[marker.end():])) if marker else ""

    title_source = series_source
    series_marker = _SXXEYY.search(title_source) or _NxNN.search(title_source)
    title_part = title_source[:series_marker.start()] if series_marker else title_source
    title_part = _strip_noise(title_part)
    year_match = _year_re.search(title_part)
    year = int(year_match.group(1)) if year_match else None
    if year_match:
        title_part = title_part[:year_match.start()]
    series = _strip_trailing_punct(title_part)
    if not series:
        series = _strip_trailing_punct(clean_words(path.parent.parent.name))
    return ParsedEpisode(series=series, season=season, episode=episode, year=year,
                         guessed_title=guessed_title)
