"""TheTVDB (v4) als alternative Primaerquelle fuer Serien."""
from __future__ import annotations

import threading
import time

import requests

from ..i18n import _
from .base import (
    SERIES, Candidate, EpisodeInfo, MediaInfo, MetadataProvider, MissingEpisode,
    SearchQuery,
)
from .cache import ResponseCache

API_BASE = "https://api4.thetvdb.com/v4"
MIN_INTERVAL = 0.1
TOKEN_TTL_DAYS = 25


class TVDBProvider(MetadataProvider):
    name = "tvdb"
    label = "TheTVDB"
    has_covers = True
    supports_series = True

    def __init__(self, api_key: str, pin: str = ""):
        self.api_key = (api_key or "").strip()
        self.pin = (pin or "").strip()
        self._session = requests.Session()
        self._last_call = 0.0
        self._lock = threading.Lock()
        self._cache = ResponseCache("tvdb.sqlite")
        self._token_cache = ResponseCache("tvdb_token.sqlite", ttl_days=TOKEN_TTL_DAYS)

    def available(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, _("Kein API-Key hinterlegt.")
        return True, ""

    def _token(self) -> str:
        cached = self._token_cache.get(self.api_key)
        if cached:
            return cached["token"]
        payload = {"apikey": self.api_key}
        if self.pin:
            payload["pin"] = self.pin
        response = self._session.post(f"{API_BASE}/login", json=payload, timeout=15)
        response.raise_for_status()
        token = response.json()["data"]["token"]
        self._token_cache.put(self.api_key, {"token": token})
        return token

    def _get(self, endpoint: str, params: dict | None = None) -> dict:
        params = params or {}
        key = endpoint + "?" + "&".join(
            f"{k}={v}" for k, v in sorted(params.items()))
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        with self._lock:
            wait = MIN_INTERVAL - (time.time() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            headers = {"Authorization": f"Bearer {self._token()}"}
            response = self._session.get(
                API_BASE + endpoint, params=params, headers=headers, timeout=15)
            self._last_call = time.time()
        response.raise_for_status()
        data = response.json()
        self._cache.put(key, data)
        return data

    def search(self, query: SearchQuery, limit: int = 10) -> list[Candidate]:
        data = self._get("/search", {"query": query.title, "type": "series"})
        results = data.get("data", [])
        return [
            Candidate(
                source=self.name, external_id=str(r.get("tvdb_id") or r.get("id")),
                kind=SERIES, title=r.get("name") or "",
                year=_year(r.get("year")),
                overview=r.get("overview") or "",
                poster_url=r.get("image_url"),
            ) for r in results[:limit]
        ]

    def details(self, candidate: Candidate) -> MediaInfo:
        data = self._get(f"/series/{candidate.external_id}/extended").get("data", {})
        genres = [g.get("name") for g in data.get("genres", []) if g.get("name")]
        return MediaInfo(
            kind=SERIES, title=data.get("name") or candidate.title,
            year=_year(data.get("year")) or candidate.year,
            overview=data.get("overview") or candidate.overview,
            genres=genres,
            poster_url=data.get("image") or candidate.poster_url,
            source=self.name, external_id=candidate.external_id,
            series_title=data.get("name") or candidate.title,
        )

    def episode_by_id(self, episode_id: str) -> dict:
        """Roh-Episodendaten per TVDB-Episoden-ID (z. B. aus einem Link wie
        thetvdb.com/series/<slug>/episodes/<id>) - liefert u. a. seriesId,
        seasonNumber und number, damit sich Serie und Staffel/Episode daraus
        ohne Umweg ueber die Suche bestimmen lassen."""
        return self._get(f"/episodes/{episode_id}").get("data", {})

    def episode(self, series_id: str, season: int,
               episode: int) -> EpisodeInfo | None:
        for page in range(3):
            data = self._get(f"/series/{series_id}/episodes/official",
                             {"page": page})
            episodes = (data.get("data") or {}).get("episodes", [])
            if not episodes:
                break
            for ep in episodes:
                if ep.get("seasonNumber") == season and \
                        ep.get("number") == episode:
                    return EpisodeInfo(
                        title=ep.get("name") or "",
                        overview=ep.get("overview") or "",
                        air_date=ep.get("aired") or "")
            links = data.get("links") or {}
            if not links.get("next"):
                break
        return None

    def series_roster(self, series_id: str) -> list[MissingEpisode]:
        """Alle Episoden der Serie - Grundlage fuer die Staffelauswahl beim
        manuellen Umbuchen (siehe MainWindow._reassign_season)."""
        result: list[MissingEpisode] = []
        for page in range(10):
            data = self._get(f"/series/{series_id}/episodes/official", {"page": page})
            episodes = (data.get("data") or {}).get("episodes", [])
            if not episodes:
                break
            for ep in episodes:
                season, number = ep.get("seasonNumber"), ep.get("number")
                if season is None or number is None:
                    continue
                result.append(MissingEpisode(
                    season=season, episode=number, title=ep.get("name") or ""))
            links = data.get("links") or {}
            if not links.get("next"):
                break
        return result


def _year(value) -> int | None:
    try:
        return int(str(value)[:4])
    except (TypeError, ValueError):
        return None
