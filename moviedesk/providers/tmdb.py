"""TMDb (The Movie Database) als Metadaten-Quelle fuer Filme und Serien."""
from __future__ import annotations

import threading
import time

import requests

from ..i18n import _
from .base import (
    MOVIE, SERIES, Candidate, EpisodeInfo, MediaInfo, MetadataProvider,
    MissingEpisode, MissingMovie, MovieExtra, SearchQuery, SeriesExtra,
)
from .cache import ResponseCache

API_BASE = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/w500"
USER_AGENT = "MovieDesk/1.0"
MIN_INTERVAL = 0.05


class TMDbProvider(MetadataProvider):
    name = "tmdb"
    label = "TMDb"
    has_covers = True
    supports_movies = True
    supports_series = True

    def __init__(self, api_key: str, language: str = "en-US"):
        self.api_key = (api_key or "").strip()
        self.language = language or "en-US"
        self._session = requests.Session()
        self._session.headers["User-Agent"] = USER_AGENT
        self._last_call = 0.0
        self._lock = threading.Lock()
        self._cache = ResponseCache("tmdb.sqlite")

    def available(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, _("Kein API-Key hinterlegt.")
        return True, ""

    def _get(self, endpoint: str, params: dict) -> dict:
        params = {"language": self.language, **params, "api_key": self.api_key}
        key = endpoint + "?" + "&".join(
            f"{k}={v}" for k, v in sorted(params.items()) if k != "api_key")
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        with self._lock:
            wait = MIN_INTERVAL - (time.time() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            response = self._session.get(
                API_BASE + endpoint, params=params, timeout=15)
            self._last_call = time.time()
        response.raise_for_status()
        data = response.json()
        self._cache.put(key, data)
        return data

    def _poster(self, path: str | None) -> str | None:
        return f"{IMAGE_BASE}{path}" if path else None

    def search(self, query: SearchQuery, limit: int = 10) -> list[Candidate]:
        if query.kind == MOVIE:
            # Kein Jahresfilter: unser geratenes Jahr ist manchmal falsch
            # (z. B. Teil des Titels wie bei "Wonder Woman 1984") - ein
            # harter Filter wuerde den richtigen Treffer dann verstecken.
            # Das Jahr fliesst stattdessen nur in die Bewertung ein.
            data = self._get("/search/movie", {"query": query.title})
            results = data.get("results", [])
            return [
                Candidate(
                    source=self.name, external_id=str(r["id"]), kind=MOVIE,
                    title=r.get("title") or r.get("original_title") or "",
                    year=_year(r.get("release_date")),
                    overview=r.get("overview") or "",
                    poster_url=self._poster(r.get("poster_path")),
                    rating=r.get("vote_average") or None,
                ) for r in results[:limit]
            ]
        data = self._get("/search/tv", {"query": query.title})
        results = data.get("results", [])
        return [
            Candidate(
                source=self.name, external_id=str(r["id"]), kind=SERIES,
                title=r.get("name") or r.get("original_name") or "",
                year=_year(r.get("first_air_date")),
                overview=r.get("overview") or "",
                poster_url=self._poster(r.get("poster_path")),
                rating=r.get("vote_average") or None,
            ) for r in results[:limit]
        ]

    def details(self, candidate: Candidate) -> MediaInfo:
        if candidate.kind == MOVIE:
            data = self._get(f"/movie/{candidate.external_id}",
                             {"append_to_response": "external_ids"})
            return MediaInfo(
                kind=MOVIE, title=data.get("title") or candidate.title,
                year=_year(data.get("release_date")) or candidate.year,
                overview=data.get("overview") or candidate.overview,
                genres=[g["name"] for g in data.get("genres", [])],
                rating=data.get("vote_average") or candidate.rating,
                poster_url=self._poster(data.get("poster_path"))
                or candidate.poster_url,
                runtime=data.get("runtime"),
                source=self.name, external_id=candidate.external_id,
                imdb_id=(data.get("external_ids") or {}).get("imdb_id"),
                collection=(data.get("belongs_to_collection") or {}).get("name") or "",
                collection_id=str((data.get("belongs_to_collection") or {}).get("id") or "")
                or "",
            )
        data = self._get(f"/tv/{candidate.external_id}",
                         {"append_to_response": "external_ids"})
        runtimes = data.get("episode_run_time") or []
        return MediaInfo(
            kind=SERIES, title=data.get("name") or candidate.title,
            year=_year(data.get("first_air_date")) or candidate.year,
            overview=data.get("overview") or candidate.overview,
            genres=[g["name"] for g in data.get("genres", [])],
            rating=data.get("vote_average") or candidate.rating,
            poster_url=self._poster(data.get("poster_path"))
            or candidate.poster_url,
            runtime=runtimes[0] if runtimes else None,
            source=self.name, external_id=candidate.external_id,
            imdb_id=(data.get("external_ids") or {}).get("imdb_id"),
            series_title=data.get("name") or candidate.title,
        )

    def episode(self, series_id: str, season: int,
               episode: int) -> EpisodeInfo | None:
        try:
            data = self._get(f"/tv/{series_id}/season/{season}/episode/{episode}", {})
        except requests.HTTPError:
            return None
        if "name" not in data:
            return None
        return EpisodeInfo(
            title=data.get("name") or "", overview=data.get("overview") or "",
            air_date=data.get("air_date") or "")

    # --- Zusatzfunktionen fuer NFO-Export und Fehlt-Vergleich -------------
    def movie_extra(self, external_id: str) -> MovieExtra:
        data = self._get(f"/movie/{external_id}",
                         {"append_to_response": "credits,keywords,release_dates"})
        crew = (data.get("credits") or {}).get("crew", [])
        return MovieExtra(
            original_title=data.get("original_title") or "",
            tagline=data.get("tagline") or "",
            release_date=data.get("release_date") or "",
            directors=[c["name"] for c in crew if c.get("job") == "Director"],
            writers=[c["name"] for c in crew
                    if c.get("job") in ("Writer", "Screenplay")],
            studios=[c["name"] for c in data.get("production_companies", [])],
            countries=[c["name"] for c in data.get("production_countries", [])],
            keywords=[k["name"] for k in
                     (data.get("keywords") or {}).get("keywords", [])],
            certification=_certification(
                (data.get("release_dates") or {}).get("results", []),
                self.language, "release_dates", "certification"),
            backdrop_url=self._poster(data.get("backdrop_path")),
        )

    def series_extra(self, external_id: str) -> SeriesExtra:
        data = self._get(f"/tv/{external_id}",
                         {"append_to_response": "credits,keywords,content_ratings"})
        return SeriesExtra(
            original_title=data.get("original_name") or "",
            tagline=data.get("tagline") or "",
            creators=[c["name"] for c in data.get("created_by", [])],
            studios=[c["name"] for c in data.get("production_companies", [])],
            countries=list(data.get("origin_country", [])),
            keywords=[k["name"] for k in
                     (data.get("keywords") or {}).get("results", [])],
            certification=_certification(
                (data.get("content_ratings") or {}).get("results", []),
                self.language, None, "rating"),
            backdrop_url=self._poster(data.get("backdrop_path")),
        )

    def collection_movies(self, collection_id: str, country: str = "") -> list[MissingMovie]:
        data = self._get(f"/collection/{collection_id}", {})
        result = []
        for p in data.get("parts", []):
            release_date = p.get("release_date") or ""
            if country:
                country_date = self._country_release_date(str(p["id"]), country)
                if country_date is not None:
                    release_date = country_date
            result.append(MissingMovie(
                tmdb_id=str(p["id"]), title=p.get("title") or "",
                year=_year(p.get("release_date")),
                poster_url=self._poster(p.get("poster_path")),
                release_date=release_date))
        return result

    def _country_release_date(self, movie_id: str, country: str) -> str | None:
        """Fruehestes Veroeffentlichungsdatum fuer `country` laut TMDb - None,
        wenn TMDb dafuer keinen Eintrag hat (dann bleibt das weltweite Datum
        als Rueckfall bestehen, siehe `collection_movies`)."""
        try:
            data = self._get(f"/movie/{movie_id}/release_dates", {})
        except requests.HTTPError:
            return None
        for entry in data.get("results", []):
            if entry.get("iso_3166_1") != country:
                continue
            dates = [d.get("release_date") for d in entry.get("release_dates", [])
                     if d.get("release_date")]
            if dates:
                return min(dates)[:10]
        return None

    def series_roster(self, series_id: str) -> list[MissingEpisode]:
        data = self._get(f"/tv/{series_id}", {})
        result: list[MissingEpisode] = []
        for season in data.get("seasons", []):
            number = season.get("season_number")
            if not number:  # 0 = Specials, meist nicht Teil der Zaehlung
                continue
            season_data = self._get(f"/tv/{series_id}/season/{number}", {})
            for ep in season_data.get("episodes", []):
                result.append(MissingEpisode(
                    season=number, episode=ep.get("episode_number"),
                    title=ep.get("name") or "", air_date=ep.get("air_date") or ""))
        return result

    def find_by_imdb(self, imdb_id: str) -> dict:
        """TMDb kennt zu einer IMDb-ID oft einen Eintrag, auch wenn andere
        Quellen (z. B. TheTVDB) sie nicht fuehren. Liefert die Rohantwort
        mit `movie_results`/`tv_results` - leer, wenn TMDb sie nicht kennt."""
        return self._get(f"/find/{imdb_id}", {"external_source": "imdb_id"})


def _certification(entries: list[dict], language: str,
                   inner_key: str | None, cert_field: str) -> str:
    """Altersfreigabe fuers Land aus der Oberflaechensprache, sonst US."""
    country = language.split("-")[-1].upper() if "-" in language else "US"
    for entry in entries:
        if entry.get("iso_3166_1") != country:
            continue
        if inner_key:
            for sub in entry.get(inner_key, []):
                cert = sub.get(cert_field)
                if cert:
                    return cert
        else:
            cert = entry.get(cert_field)
            if cert:
                return cert
    return ""


def _year(date_str: str | None) -> int | None:
    if not date_str or len(date_str) < 4:
        return None
    try:
        return int(date_str[:4])
    except ValueError:
        return None
