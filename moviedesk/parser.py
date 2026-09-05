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

#: Weitere Episode eines Mehrteilers direkt nach dem ersten Treffer -
#: "S01E01E02" (kein Trenner) oder "S01E01 E02"/"S01E01 02" (der Bindestrich
#: dazwischen wurde von clean_words() schon zu einem Leerzeichen). Ohne das
#: wuerde "S01E01E02" nur als E01 erkannt und die zweite Episode verschwaende
#: stillschweigend.
#: Kein "^"/"\A" hier - match() mit pos-Argument setzt den Suchstart schon
#: exakt dorthin, ein zusaetzlicher Anfangsanker wuerde an der echten
#: Stringposition 0 verankern statt an pos und liefe dadurch immer leer.
_EXTRA_EP = re.compile(r"\s?[Ee](\d{1,3})(?![a-zA-Z\d])")
_EXTRA_EP_BARE = re.compile(r"\s(\d{1,3})(?![a-zA-Z\d])")

#: Anime-Fallback: durchlaufende Episodennummer ohne SxxEyy/Staffelordner,
#: z. B. "[Gruppe] Serie - 05 [1080p].mkv". Nur ein Notbehelf - findet
#: sich keine plausible Zahl, bleibt die Datei unerkannt statt falsch
#: geraten zu werden.
_ANIME_ABS = re.compile(r"(?:\A|\s)(\d{1,3})(?![a-zA-Z\d])")
#: Gaengige Aufloesungen als blanke Zahl - keine Episodennummern, auch wenn
#: sie die obige Form erfuellen.
_RESOLUTIONS = {"240", "360", "480", "576", "720", "1080", "2160"}

#: Fansub-Gruppenname vorangestellt in eckigen Klammern, z. B.
#: "[SubGroup] Serie - 05.mkv" - sonst landet "]" mitten im Serientitel.
_LEADING_TAG = re.compile(r"^\[[^\]]*\]\s*")

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
    #: Letzte Episode eines Mehrteilers ("S01E01E02" -> episode=1, episode_end=2),
    #: sonst None. Beide Nummern liegen in derselben Datei.
    episode_end: int | None = None


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


def _anime_absolute_episode(text: str) -> tuple[int, int] | None:
    """Letzte plausible blanke Zahl im Namen als durchlaufende Episoden-
    nummer - gaengige Anime-Konvention ohne Staffelangabe (Staffel 1
    angenommen, wie die meisten Verwaltungsprogramme das handhaben).
    Gibt (Position, Episodennummer) zurueck, oder None ohne Kandidaten."""
    candidates = [m for m in _ANIME_ABS.finditer(text)
                 if m.group(1) not in _RESOLUTIONS]
    if not candidates:
        return None
    match = candidates[-1]
    return match.start(1), int(match.group(1))


def parse_episode(path: Path) -> ParsedEpisode | None:
    """Serienname + Staffel/Episode. None, wenn kein Muster erkennbar ist.

    Sucht zuerst im Dateinamen; fehlt dort die Staffel (z. B. nur `E05.mkv`
    in einem `Season 01`-Ordner), wird der Ordner herangezogen. Letzter
    Rueckfall: eine durchlaufende Nummer ohne jede Staffelangabe, wie bei
    Anime-Releases ueblich (siehe `_anime_absolute_episode`).
    """
    stem = clean_words(path.stem)
    found = _season_episode(stem)
    series_source = stem
    marker_source = stem
    #: Position, ab der der Serientitel abgeschnitten wird - normalerweise
    #: der Start des SxxEyy-Treffers, beim Anime-Fallback die Zahl selbst.
    cut_at: int | None = None

    if found is None:
        season_match = _SEASON_ONLY.search(path.parent.name) or \
            _SEASON_WORD.search(path.parent.name)
        episode_match = _EPISODE_WORD.search(stem) or \
            re.search(r"\b[Ee](\d{1,3})\b", stem)
        if season_match and episode_match:
            found = (int(season_match.group(1)), int(episode_match.group(1)))
            series_source = clean_words(path.parent.parent.name)

    if found is None:
        absolute = _anime_absolute_episode(stem)
        if absolute is not None:
            cut_at, abs_episode = absolute
            found = (1, abs_episode)

    if found is None:
        return None

    season, episode = found
    episode_end: int | None = None
    marker = _SXXEYY.search(marker_source) or _NxNN.search(marker_source)
    if marker:
        # Mehrteiler wie "S01E01E02"/"S01E01 E02"/"S01E01 02" (der
        # Bindestrich ist durch clean_words() schon zu einem Leerzeichen
        # geworden) - weitere Episoden direkt nach dem ersten Treffer
        # einsammeln, statt sie stillschweigend zu verlieren.
        pos = marker.end()
        while True:
            extra = _EXTRA_EP.match(marker_source, pos) or \
                _EXTRA_EP_BARE.match(marker_source, pos)
            if not extra:
                break
            episode_end = int(extra.group(1))
            pos = extra.end()
        guessed_title = _strip_trailing_punct(_strip_noise(marker_source[pos:]))
    else:
        guessed_title = ""

    title_source = series_source
    if cut_at is not None:
        title_part = title_source[:cut_at]
    else:
        series_marker = _SXXEYY.search(title_source) or _NxNN.search(title_source)
        title_part = title_source[:series_marker.start()] if series_marker \
            else title_source
    title_part = _LEADING_TAG.sub("", title_part)
    title_part = _strip_noise(title_part)
    year_match = _year_re.search(title_part)
    year = int(year_match.group(1)) if year_match else None
    if year_match:
        title_part = title_part[:year_match.start()]
    series = _strip_trailing_punct(title_part)
    if not series:
        series = _strip_trailing_punct(clean_words(path.parent.parent.name))
    return ParsedEpisode(series=series, season=season, episode=episode, year=year,
                         guessed_title=guessed_title, episode_end=episode_end)
