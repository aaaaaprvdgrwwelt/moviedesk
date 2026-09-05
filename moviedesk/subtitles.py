"""Untertitel von OpenSubtitles.com suchen und herunterladen.

Separate REST-API (kein Filmkatalog wie TMDb/OMDb/TVDB, daher kein
MetadataProvider): Suche funktioniert mit blossem API-Key, Herunterladen
braucht zusaetzlich einen eingeloggten Account - sonst gilt nur ein sehr
kleines Tages-Limit fuer anonyme Anfragen.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests
from PySide6.QtCore import QObject, QThread, Signal

from .i18n import _
from .library import EPISODE, Item

API_BASE = "https://api.opensubtitles.com/api/v1"
USER_AGENT = "MovieDesk v0.1"
MIN_INTERVAL = 0.3

DEFAULT_LANGUAGES = "de,en"


class OpenSubtitlesError(RuntimeError):
    pass


@dataclass
class SubtitleQuery:
    title: str
    year: int | None = None
    #: Film: eigene TMDb-ID. Episode: TMDb-ID der Serie (`parent_tmdb_id`).
    tmdb_id: str | None = None
    parent_tmdb_id: str | None = None
    season: int | None = None
    episode: int | None = None
    languages: list[str] = field(default_factory=list)


@dataclass
class SubtitleResult:
    file_id: int
    language: str
    release: str
    download_count: int
    rating: float
    hearing_impaired: bool
    file_name: str


def query_for_item(item: Item, languages: list[str]) -> SubtitleQuery:
    tmdb_id = item.external_id if item.source == "tmdb" else None
    if item.kind == EPISODE:
        return SubtitleQuery(title=item.title, parent_tmdb_id=tmdb_id,
                             season=item.season, episode=item.episode,
                             languages=languages)
    return SubtitleQuery(title=item.title, year=item.year, tmdb_id=tmdb_id,
                         languages=languages)


def missing_languages(path: Path, languages: list[str]) -> list[str]:
    """Sprachen, fuer die noch keine `.srt` neben der Datei liegt.

    Eine Datei ohne Sprachkuerzel (`Film.srt`) gilt als Erfuellung der
    zuerst konfigurierten Sprache - so benennen viele Bibliotheken ihre
    einzige/Standard-Untertitelspur.
    """
    missing: list[str] = []
    for i, lang in enumerate(languages):
        tagged = path.with_suffix(f".{lang}.srt")
        bare = path.with_suffix(".srt")
        if tagged.exists() or (i == 0 and bare.exists()):
            continue
        missing.append(lang)
    return missing


def best_result(results: list[SubtitleResult], language: str) -> SubtitleResult | None:
    """Bester Treffer je Sprache: meiste Downloads, dann beste Bewertung."""
    candidates = [r for r in results if r.language == language]
    if not candidates:
        return None
    return max(candidates, key=lambda r: (r.download_count, r.rating))


class OpenSubtitlesClient:
    def __init__(self, api_key: str, username: str = "", password: str = ""):
        self.api_key = (api_key or "").strip()
        self.username = (username or "").strip()
        self.password = password or ""
        self._session = requests.Session()
        self._session.headers.update({
            "Api-Key": self.api_key,
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        self._token: str | None = None
        self._last_call = 0.0
        self._lock = threading.Lock()

    def available(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, _("Kein API-Key hinterlegt.")
        return True, ""

    def _throttle(self) -> None:
        with self._lock:
            wait = MIN_INTERVAL - (time.time() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.time()

    def _login(self) -> None:
        if self._token or not self.username or not self.password:
            return
        self._throttle()
        response = self._session.post(
            f"{API_BASE}/login",
            json={"username": self.username, "password": self.password},
            timeout=15)
        response.raise_for_status()
        self._token = response.json().get("token")
        if self._token:
            self._session.headers["Authorization"] = f"Bearer {self._token}"

    def search(self, query: SubtitleQuery) -> list[SubtitleResult]:
        params: dict = {"languages": ",".join(query.languages)}
        if query.parent_tmdb_id:
            params["parent_tmdb_id"] = query.parent_tmdb_id
            if query.season is not None:
                params["season_number"] = query.season
            if query.episode is not None:
                params["episode_number"] = query.episode
        elif query.tmdb_id:
            params["tmdb_id"] = query.tmdb_id
        else:
            params["query"] = query.title
            if query.year:
                params["year"] = query.year
        self._throttle()
        response = self._session.get(f"{API_BASE}/subtitles", params=params, timeout=15)
        response.raise_for_status()
        results: list[SubtitleResult] = []
        for entry in response.json().get("data", []):
            attrs = entry.get("attributes", {})
            files = attrs.get("files") or []
            if not files:
                continue
            results.append(SubtitleResult(
                file_id=files[0]["file_id"],
                language=attrs.get("language", ""),
                release=attrs.get("release", ""),
                download_count=attrs.get("download_count", 0) or 0,
                rating=float(attrs.get("ratings", 0) or 0),
                hearing_impaired=bool(attrs.get("hearing_impaired")),
                file_name=files[0].get("file_name", ""),
            ))
        return results

    def download(self, result: SubtitleResult) -> bytes:
        self._login()
        self._throttle()
        response = self._session.post(
            f"{API_BASE}/download", json={"file_id": result.file_id}, timeout=15)
        if response.status_code == 406:
            raise OpenSubtitlesError(
                _("Tages-Limit fuer Untertitel-Downloads erreicht."))
        response.raise_for_status()
        link = response.json().get("link")
        if not link:
            raise OpenSubtitlesError(_("Kein Download-Link erhalten."))
        self._throttle()
        file_response = self._session.get(link, timeout=30)
        file_response.raise_for_status()
        return file_response.content


# ---------------------------------------------------------------------------
STATUS_OK = "ok"
STATUS_NONE = "kein_treffer"
STATUS_ERROR = "fehler"


@dataclass
class SubtitleDownloadResult:
    path: Path
    language: str
    status: str
    detail: str = ""


class SubtitleDownloadWorker(QObject):
    """Laeuft im eigenen Thread, meldet pro Sprache/Datei ein Ergebnis."""

    progress = Signal(int, int, str)
    result = Signal(object)
    finished = Signal()

    def __init__(self, jobs: list[tuple[Item, list[str]]],
                client: OpenSubtitlesClient):
        super().__init__()
        self.jobs = jobs
        self.client = client
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        total = sum(len(langs) for _, langs in self.jobs)
        done = 0
        for item, languages in self.jobs:
            if self._stop:
                break
            path = Path(item.path)
            try:
                results = self.client.search(query_for_item(item, languages))
                notes = ""
            except Exception as exc:  # noqa: BLE001
                results, notes = [], str(exc)
            for lang in languages:
                if self._stop:
                    break
                done += 1
                self.progress.emit(done, total, path.name)
                best = best_result(results, lang)
                if best is None:
                    self.result.emit(
                        SubtitleDownloadResult(path, lang, STATUS_NONE, notes))
                    continue
                try:
                    data = self.client.download(best)
                    target = path.with_suffix(f".{lang}.srt")
                    target.write_bytes(data)
                    self.result.emit(
                        SubtitleDownloadResult(path, lang, STATUS_OK))
                except Exception as exc:  # noqa: BLE001
                    self.result.emit(
                        SubtitleDownloadResult(path, lang, STATUS_ERROR, str(exc)))
        self.finished.emit()


def run_in_thread(jobs: list[tuple[Item, list[str]]], client: OpenSubtitlesClient):
    """Gibt (thread, worker) zurueck - der Aufrufer verbindet die Signale."""
    thread = QThread()
    worker = SubtitleDownloadWorker(jobs, client)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    return thread, worker
