"""NFO-Dateien fuer Kodi/Jellyfin/Plex erzeugen.

Reine Zusatzdatei neben der Videodatei (bzw. `tvshow.nfo` im Serienordner) -
aendert nichts an der Videodatei selbst und nichts am eigenen Bibliotheksindex.
Wird nur auf ausdruecklichen Nutzerwunsch geschrieben, nie automatisch.

Cast-Fotos, Wiedergabestatus und technische Stream-Infos (Codec/Aufloesung)
werden bewusst nicht nachgebaut - die ermitteln Kodi/Jellyfin beim eigenen
Scan der Datei ohnehin selbst, zuverlaessiger als eine Vermutung von hier aus.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import requests

from .library import Item, MOVIE
from .providers.base import MetadataProvider, MovieExtra, SeriesExtra


def _write(root: ET.Element, path: Path) -> None:
    ET.indent(root, space="  ")
    tree = ET.ElementTree(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(path, encoding="utf-8", xml_declaration=True)


def _add_genres_and_ids(el: ET.Element, item: Item) -> None:
    for genre in item.genres:
        ET.SubElement(el, "genre").text = genre
    if item.external_id and item.source == "tmdb":
        ET.SubElement(el, "uniqueid", type="tmdb",
                     default="true").text = item.external_id
        # Flache <tmdbid>-Angabe zusaetzlich zu <uniqueid> - manche (auch
        # aeltere) Kodi-Scraper und Drittwerkzeuge lesen nur diese Form.
        ET.SubElement(el, "tmdbid").text = item.external_id
    if item.imdb_id:
        ET.SubElement(el, "uniqueid", type="imdb").text = item.imdb_id
        ET.SubElement(el, "imdbid").text = item.imdb_id


def _add_common_extra(el: ET.Element, original_title: str, tagline: str,
                      studios: list[str], countries: list[str],
                      keywords: list[str], certification: str,
                      backdrop_url: str | None) -> None:
    if original_title:
        ET.SubElement(el, "originaltitle").text = original_title
    if tagline:
        ET.SubElement(el, "tagline").text = tagline
    if certification:
        ET.SubElement(el, "mpaa").text = certification
    for country in countries:
        ET.SubElement(el, "country").text = country
    for studio in studios:
        ET.SubElement(el, "studio").text = studio
    for keyword in keywords:
        ET.SubElement(el, "tag").text = keyword
    if backdrop_url:
        art = el.find("art")
        if art is None:
            art = ET.SubElement(el, "art")
        ET.SubElement(art, "fanart").text = backdrop_url


def movie_nfo_path(item: Item) -> Path:
    return Path(item.path).with_suffix(".nfo")


def movie_poster_path(item: Item) -> Path:
    """Kodi/Jellyfin/Plex erkennen "poster.jpg" im Filmordner automatisch."""
    return Path(item.path).with_name("poster.jpg")


def series_poster_path(item: Item) -> Path:
    """"poster.jpg" im Serien-Wurzelordner - neben `tvshow.nfo`."""
    return tvshow_nfo_path(item).parent / "poster.jpg"


def save_poster(url: str, path: Path) -> bool:
    """Poster-Bild herunterladen und lokal ablegen. True bei Erfolg.

    Bewusst tolerant: ein fehlgeschlagener Download (kein Netz, falsche URL)
    soll das Erzeugen der NFO-Datei nicht verhindern."""
    if not url:
        return False
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
        return True
    except Exception:  # noqa: BLE001
        return False


def write_movie_nfo(item: Item, extra: MovieExtra | None = None) -> Path:
    root = ET.Element("movie")
    ET.SubElement(root, "title").text = item.title
    if item.year:
        ET.SubElement(root, "year").text = str(item.year)
    if item.overview:
        ET.SubElement(root, "plot").text = item.overview
    _add_genres_and_ids(root, item)
    if item.rating:
        ET.SubElement(root, "rating").text = f"{item.rating:.1f}"
    if item.runtime:
        ET.SubElement(root, "runtime").text = str(item.runtime)
    if item.collection:
        set_el = ET.SubElement(root, "set")
        ET.SubElement(set_el, "name").text = item.collection
    if item.poster_url:
        art = ET.SubElement(root, "art")
        ET.SubElement(art, "poster").text = item.poster_url
    if extra:
        premiered = extra.release_date
        if premiered:
            ET.SubElement(root, "premiered").text = premiered
        for director in extra.directors:
            ET.SubElement(root, "director").text = director
        for writer in extra.writers:
            ET.SubElement(root, "credits").text = writer
        _add_common_extra(root, extra.original_title, extra.tagline,
                          extra.studios, extra.countries, extra.keywords,
                          extra.certification, extra.backdrop_url)
    path = movie_nfo_path(item)
    _write(root, path)
    return path


def episode_nfo_path(item: Item) -> Path:
    return Path(item.path).with_suffix(".nfo")


def write_episode_nfo(item: Item, air_date: str = "") -> Path:
    root = ET.Element("episodedetails")
    ET.SubElement(root, "title").text = item.episode_title or item.title
    if item.season is not None:
        ET.SubElement(root, "season").text = str(item.season)
    if item.episode is not None:
        ET.SubElement(root, "episode").text = str(item.episode)
    plot = item.episode_overview or item.overview
    if plot:
        ET.SubElement(root, "plot").text = plot
    if air_date:
        ET.SubElement(root, "aired").text = air_date
    if item.external_id and item.source == "tmdb":
        ET.SubElement(root, "uniqueid", type="tmdb",
                     default="true").text = item.external_id
    path = episode_nfo_path(item)
    _write(root, path)
    return path


def tvshow_nfo_path(item: Item) -> Path:
    """Kodi/Jellyfin erwarten `tvshow.nfo` im Wurzelordner der Serie - also
    dem Ordner ueber dem Staffelordner (`Serie/Season 01/datei.mkv`)."""
    return Path(item.path).parent.parent / "tvshow.nfo"


def write_tvshow_nfo(item: Item, extra: SeriesExtra | None = None) -> Path:
    root = ET.Element("tvshow")
    ET.SubElement(root, "title").text = item.title
    if item.year:
        ET.SubElement(root, "year").text = str(item.year)
    if item.overview:
        ET.SubElement(root, "plot").text = item.overview
    _add_genres_and_ids(root, item)
    if item.poster_url:
        art = ET.SubElement(root, "art")
        ET.SubElement(art, "poster").text = item.poster_url
    if extra:
        for creator in extra.creators:
            ET.SubElement(root, "credits").text = creator
        _add_common_extra(root, extra.original_title, extra.tagline,
                          extra.studios, extra.countries, extra.keywords,
                          extra.certification, extra.backdrop_url)
    path = tvshow_nfo_path(item)
    _write(root, path)
    return path


def write_for_item(item: Item, tvshow_done: set[Path],
                   provider: MetadataProvider | None = None,
                   save_posters: bool = False) -> Path:
    """Schreibt die passende(n) NFO-Datei(en) fuer einen Bibliothekseintrag.

    `provider` ist optional: ohne ihn (oder bei Netzfehlern) entsteht die
    einfache NFO aus den bereits im Index vorhandenen Feldern. Mit
    `save_posters=True` wird zusaetzlich ein lokales "poster.jpg" abgelegt -
    das lesen Kodi/Jellyfin/Plex auch ohne Internetzugriff.
    """
    use_provider = provider if item.source == "tmdb" else None

    if item.kind == MOVIE:
        extra = None
        if use_provider:
            try:
                extra = use_provider.movie_extra(item.external_id)
            except Exception:  # noqa: BLE001
                extra = None
        if save_posters and item.poster_url:
            save_poster(item.poster_url, movie_poster_path(item))
        return write_movie_nfo(item, extra)

    air_date = ""
    if use_provider and item.season is not None and item.episode is not None:
        try:
            info = use_provider.episode(item.external_id, item.season, item.episode)
            air_date = info.air_date if info else ""
        except Exception:  # noqa: BLE001
            air_date = ""
    path = write_episode_nfo(item, air_date)

    show_folder = tvshow_nfo_path(item).parent
    if show_folder not in tvshow_done:
        extra = None
        if use_provider:
            try:
                extra = use_provider.series_extra(item.external_id)
            except Exception:  # noqa: BLE001
                extra = None
        if save_posters and item.poster_url:
            save_poster(item.poster_url, series_poster_path(item))
        write_tvshow_nfo(item, extra)
        tvshow_done.add(show_folder)
    return path
