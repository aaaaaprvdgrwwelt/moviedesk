"""OMDb (nutzt IMDb-Daten) - normalerweise nur Ergaenzung (Rating nachladen),
kann aber per IMDb-ID auch komplette Metadaten liefern, wenn TMDb/TheTVDB
eine ID nicht kennen. OMDb ist im Kern ein Wrapper um IMDbs eigene Daten,
findet also oft Titel, die TMDb (noch) nicht verknuepft hat."""
from __future__ import annotations

import threading
import time

import requests

from ..i18n import _
from .base import MOVIE, MediaInfo, MetadataProvider, ROLE_SUPPLEMENT, SearchQuery, SERIES
from .cache import ResponseCache

API_BASE = "https://www.omdbapi.com/"
MIN_INTERVAL = 0.1


class OMDbProvider(MetadataProvider):
    name = "omdb"
    label = "OMDb"
    role = ROLE_SUPPLEMENT

    def __init__(self, api_key: str):
        self.api_key = (api_key or "").strip()
        self._session = requests.Session()
        self._last_call = 0.0
        self._lock = threading.Lock()
        self._cache = ResponseCache("omdb.sqlite")

    def available(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, _("Kein API-Key hinterlegt.")
        return True, ""

    def _get(self, params: dict) -> dict:
        key = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        data = self._cache.get(key)
        if data is None:
            with self._lock:
                wait = MIN_INTERVAL - (time.time() - self._last_call)
                if wait > 0:
                    time.sleep(wait)
                response = self._session.get(
                    API_BASE, params={**params, "apikey": self.api_key}, timeout=15)
                self._last_call = time.time()
            response.raise_for_status()
            data = response.json()
            self._cache.put(key, data)
        return data

    def supplement(self, query: SearchQuery) -> dict:
        params = {"t": query.title, "type": "movie" if query.kind == MOVIE else "series"}
        if query.year:
            params["y"] = query.year
        data = self._get(params)
        if data.get("Response") != "True":
            return {}
        rating = data.get("imdbRating")
        result = {}
        if rating and rating != "N/A":
            try:
                result["rating"] = float(rating)
            except ValueError:
                pass
        plot = data.get("Plot")
        if plot and plot != "N/A":
            result["overview"] = plot
        imdb_id = data.get("imdbID")
        if imdb_id:
            result["imdb_id"] = imdb_id
        return result

    def find_by_imdb(self, imdb_id: str) -> MediaInfo | None:
        """Volle Metadaten per IMDb-ID - Rueckfallquelle, wenn TMDb diese
        ID nicht verknuepft hat. None, wenn auch OMDb sie nicht kennt."""
        data = self._get({"i": imdb_id, "plot": "full"})
        if data.get("Response") != "True":
            return None
        kind = MOVIE if data.get("Type") == "movie" else SERIES
        genres = [g.strip() for g in (data.get("Genre") or "").split(",")
                 if g.strip() and g.strip() != "N/A"]
        rating = None
        raw_rating = data.get("imdbRating")
        if raw_rating and raw_rating != "N/A":
            try:
                rating = float(raw_rating)
            except ValueError:
                pass
        runtime = None
        raw_runtime = data.get("Runtime")
        if raw_runtime and raw_runtime != "N/A":
            try:
                runtime = int(raw_runtime.split()[0])
            except (ValueError, IndexError):
                pass
        year = None
        raw_year = data.get("Year")
        if raw_year and raw_year != "N/A":
            try:
                year = int(raw_year[:4])
            except ValueError:
                pass
        plot = data.get("Plot")
        poster = data.get("Poster")
        return MediaInfo(
            kind=kind, title=data.get("Title") or "", year=year,
            overview=plot if plot and plot != "N/A" else "",
            genres=genres, rating=rating,
            poster_url=poster if poster and poster != "N/A" else None,
            runtime=runtime, source=self.name, external_id=imdb_id,
            imdb_id=imdb_id, series_title=data.get("Title") or "",
        )

    def details(self, candidate) -> MediaInfo:
        """Ueberschrieben, damit ein manuell per IMDb-ID gewaehlter Treffer
        (siehe `find_by_imdb`) auch Genres/Laufzeit behaelt - die Basisklasse
        kennt nur die schmaleren Candidate-Felder."""
        info = self.find_by_imdb(candidate.external_id)
        return info or super().details(candidate)
