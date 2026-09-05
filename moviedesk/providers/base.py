"""Gemeinsame Schnittstelle fuer Metadaten-Quellen (Filme und Serien)."""
from __future__ import annotations

from dataclasses import dataclass, field

from deskkit.matching import normalize_title, title_similarity

MOVIE = "movie"
SERIES = "series"

#: Quellen, die einen Film/eine Serie selbst bestimmen koennen.
ROLE_PRIMARY = "primary"
#: Quellen, die nur ergaenzen (z. B. IMDb-Rating). Gewinnen nie allein.
ROLE_SUPPLEMENT = "supplement"


@dataclass
class SearchQuery:
    """Was wir aus dem Dateinamen (und ggf. dem Ordner) ueber den Titel wissen."""

    kind: str                    # MOVIE oder SERIES
    title: str
    year: int | None = None
    season: int | None = None
    episode: int | None = None


@dataclass
class Candidate:
    """Ein Treffer einer Quelle - Film oder Serie, noch ohne volle Details."""

    source: str
    external_id: str
    kind: str
    title: str
    year: int | None = None
    overview: str = ""
    poster_url: str | None = None
    rating: float | None = None
    score: int = 0
    reasons: list[str] = field(default_factory=list)


@dataclass
class EpisodeInfo:
    title: str = ""
    overview: str = ""
    air_date: str = ""


@dataclass
class MediaInfo:
    """Volle Metadaten eines gewaehlten Treffers - Grundlage fuers Umbenennen."""

    kind: str
    title: str
    year: int | None = None
    overview: str = ""
    genres: list[str] = field(default_factory=list)
    rating: float | None = None
    poster_url: str | None = None
    runtime: int | None = None
    source: str = ""
    external_id: str = ""
    imdb_id: str | None = None
    #: Nur bei Serien belegt - Name der Serie (== title, aber explizit).
    series_title: str = ""
    #: Nur bei Filmen, die zu einer Filmreihe gehoeren, z. B.
    #: "The Fast and the Furious Collection".
    collection: str = ""
    #: TMDb-ID dieser Filmreihe - noetig, um spaeter die volle Liste
    #: abzufragen (siehe `MetadataProvider.collection_movies`).
    collection_id: str = ""


@dataclass
class MovieExtra:
    """Zusatzfelder fuer den NFO-Export - separat, da nicht fuers Matching
    gebraucht und daher nicht im Bibliotheksindex gespeichert."""

    original_title: str = ""
    tagline: str = ""
    release_date: str = ""
    directors: list[str] = field(default_factory=list)
    writers: list[str] = field(default_factory=list)
    studios: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    certification: str = ""
    backdrop_url: str | None = None


@dataclass
class SeriesExtra:
    original_title: str = ""
    tagline: str = ""
    creators: list[str] = field(default_factory=list)
    studios: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    certification: str = ""
    backdrop_url: str | None = None


@dataclass
class MissingMovie:
    """Ein Film einer Filmreihe, der (noch) nicht in der Bibliothek liegt."""

    tmdb_id: str
    title: str
    year: int | None = None
    poster_url: str | None = None
    #: Veroeffentlichungsdatum (ISO, "YYYY-MM-DD") - laenderspezifisch, falls
    #: beim Abruf ein Land angegeben wurde, sonst das weltweite TMDb-Datum.
    release_date: str = ""


@dataclass
class MissingEpisode:
    """Eine laut TMDb existierende Episode ohne eigene Datei."""

    season: int
    episode: int
    title: str = ""
    #: Ausstrahlungsdatum (ISO, "YYYY-MM-DD") - TMDb kennt dafuer kein
    #: Land, nur ein einziges (weltweites) Datum je Episode.
    air_date: str = ""


class MetadataProvider:
    """Basisklasse. `search` liefert Kandidaten, `details`/`episode` vertiefen."""

    name = "base"
    label = "Basis"
    has_covers = False
    role = ROLE_PRIMARY
    #: Kann diese Quelle Serien (mit Episoden) beantworten?
    supports_series = False
    supports_movies = False

    def available(self) -> tuple[bool, str]:
        """(nutzbar, Begruendung falls nicht)."""
        return False, "Nicht konfiguriert"

    def search(self, query: SearchQuery, limit: int = 10) -> list[Candidate]:
        raise NotImplementedError

    def details(self, candidate: Candidate) -> MediaInfo:
        """Volle Metadaten fuer den Gewinner - erst hier noetig."""
        return MediaInfo(
            kind=candidate.kind, title=candidate.title, year=candidate.year,
            overview=candidate.overview, rating=candidate.rating,
            poster_url=candidate.poster_url, source=candidate.source,
            external_id=candidate.external_id, series_title=candidate.title,
        )

    def episode(self, series_id: str, season: int,
                episode: int) -> EpisodeInfo | None:
        """Nur fuer Serienquellen: Titel/Beschreibung einer einzelnen Folge."""
        return None

    def supplement(self, query: SearchQuery) -> dict:
        """Nur fuer Ergaenzungsquellen: Felder, die eine Primaerquelle offen
        gelassen hat (z. B. IMDb-Rating). Leeres Dict, wenn nichts gefunden."""
        return {}

    # --- Optionale Zusatzfunktionen (nur TMDb implementiert sie bisher) ---
    def movie_extra(self, external_id: str) -> MovieExtra | None:
        """Zusatzfelder fuer den NFO-Export - Regie, Studios, Keywords, ..."""
        return None

    def series_extra(self, external_id: str) -> SeriesExtra | None:
        return None

    def collection_movies(self, collection_id: str, country: str = "") -> list[MissingMovie]:
        """Alle Filme einer Filmreihe laut Quelle - fuer den Fehlt-Vergleich.
        `country` (ISO 3166-1, z. B. "DE"): falls angegeben und von der
        Quelle unterstuetzt, `release_date` je Film fuer dieses Land statt
        weltweit."""
        return []

    def series_roster(self, series_id: str) -> list[MissingEpisode]:
        """Alle Episoden einer Serie laut Quelle - fuer den Fehlt-Vergleich."""
        return []
