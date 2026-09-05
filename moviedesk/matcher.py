"""Kandidaten bewerten und automatisch zuordnen."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from .i18n import _
from .library import (
    LibraryIndex, STATUS_ERROR, STATUS_MATCHED, STATUS_UNMATCHED, STATUS_UNSURE,
)
from .parser import parse_episode, parse_movie
from .providers.base import (
    MOVIE, ROLE_PRIMARY, ROLE_SUPPLEMENT, SERIES, Candidate, EpisodeInfo,
    MediaInfo, MetadataProvider, SearchQuery, title_similarity,
)

DEFAULT_THRESHOLD = 70

W_TITLE = 70
W_YEAR = 30


@dataclass
class MatchConfig:
    threshold: int = DEFAULT_THRESHOLD
    providers: list[MetadataProvider] = field(default_factory=list)


def score_candidate(query: SearchQuery, candidate: Candidate) -> int:
    parts: list[tuple[int, float]] = [
        (W_TITLE, title_similarity(query.title, candidate.title))
    ]
    if query.year and candidate.year:
        delta = abs(query.year - candidate.year)
        parts.append((W_YEAR, 1.0 if delta == 0 else 0.5 if delta == 1 else 0.0))
    total_weight = sum(w for w, _ in parts)
    if not total_weight:
        return 0
    return round(100 * sum(w * v for w, v in parts) / total_weight)


def collect_candidates(query: SearchQuery, config: MatchConfig,
                       should_stop: Callable[[], bool] | None = None
                       ) -> tuple[list[Candidate], str]:
    stopped = should_stop or (lambda: False)
    found: list[Candidate] = []
    notes: list[str] = []
    for provider in config.providers:
        if stopped():
            break
        if provider.role != ROLE_PRIMARY:
            continue
        if query.kind == MOVIE and not provider.supports_movies:
            continue
        if query.kind == SERIES and not provider.supports_series:
            continue
        ok, why = provider.available()
        if not ok:
            notes.append(f"{_(provider.label)}: {why}")
            continue
        try:
            candidates = provider.search(query)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"{_(provider.label)}: {exc}")
            continue
        for candidate in candidates:
            candidate.score = score_candidate(query, candidate)
            found.append(candidate)
    found.sort(key=lambda c: -c.score)
    return found, "; ".join(notes)


def identify(query: SearchQuery, config: MatchConfig,
            should_stop: Callable[[], bool] | None = None
            ) -> tuple[Candidate | None, str]:
    found, notes = collect_candidates(query, config, should_stop)
    return (found[0] if found else None), notes


SUPPLEMENT_FIELDS = ("rating", "overview", "imdb_id")


def apply_supplements(info: MediaInfo, query: SearchQuery,
                      providers: list[MetadataProvider]) -> list[str]:
    """Leerstellen (v. a. IMDb-Rating) von Ergaenzungsquellen fuellen."""
    used: list[str] = []
    for provider in providers:
        if provider.role != ROLE_SUPPLEMENT or not provider.available()[0]:
            continue
        try:
            extra = provider.supplement(query)
        except Exception:  # noqa: BLE001
            continue
        if not extra:
            continue
        filled = False
        for field_name in SUPPLEMENT_FIELDS:
            value = extra.get(field_name)
            if value and not getattr(info, field_name, None):
                setattr(info, field_name, value)
                filled = True
        if filled:
            used.append(provider.label)
    return used


def _episode_details(provider: MetadataProvider, series_id: str, season: int,
                     episode: int) -> EpisodeInfo:
    try:
        info = provider.episode(series_id, season, episode)
    except Exception:  # noqa: BLE001
        return EpisodeInfo()
    return info or EpisodeInfo()


@dataclass
class MatchResult:
    path: Path
    status: str
    score: int = 0
    source: str = ""
    summary: str = ""
    detail: str = ""


class AutoMatchWorker(QObject):
    """Laeuft im eigenen Thread, meldet pro Datei ein Ergebnis."""

    progress = Signal(int, int, str)   # erledigt, gesamt, Dateiname
    result = Signal(object)            # MatchResult
    finished = Signal()

    def __init__(self, movie_paths: list[Path], episode_paths: list[Path],
                config: MatchConfig, library: LibraryIndex):
        super().__init__()
        self.movie_paths = movie_paths
        self.episode_paths = episode_paths
        self.config = config
        self.library = library
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        all_paths = [(p, MOVIE) for p in self.movie_paths] + \
            [(p, SERIES) for p in self.episode_paths]
        by_source = {p.name: p for p in self.config.providers}
        for i, (path, kind) in enumerate(all_paths, 1):
            if self._stop:
                break
            self.progress.emit(i, len(all_paths), path.name)
            if kind == MOVIE:
                self.result.emit(self._match_movie(path, by_source))
            else:
                self.result.emit(self._match_episode(path, by_source))
        self.finished.emit()

    def _match_movie(self, path: Path,
                     by_source: dict[str, MetadataProvider]) -> MatchResult:
        parsed = parse_movie(path)
        if not parsed.title:
            self.library.set_status(path, STATUS_UNMATCHED,
                                    _("Kein Titel im Dateinamen erkennbar."))
            return MatchResult(path, STATUS_UNMATCHED)
        query = SearchQuery(kind=MOVIE, title=parsed.title, year=parsed.year)
        try:
            candidate, notes = identify(query, self.config, lambda: self._stop)
        except Exception as exc:  # noqa: BLE001
            self.library.set_status(path, STATUS_ERROR, str(exc))
            return MatchResult(path, STATUS_ERROR, detail=str(exc))
        if candidate is None:
            self.library.set_status(path, STATUS_UNMATCHED, notes)
            return MatchResult(path, STATUS_UNMATCHED, detail=notes)

        provider = by_source[candidate.source]
        info = provider.details(candidate)
        used = apply_supplements(info, query, self.config.providers)
        status = STATUS_MATCHED if candidate.score >= self.config.threshold \
            else STATUS_UNSURE
        note = "; ".join(filter(None, [
            notes, _("ergaenzt durch {sources}").format(
                sources=", ".join(used)) if used else ""]))
        self.library.set_match(path, info, candidate.score, status, note=note)
        summary = f"{info.title} ({info.year})" if info.year else info.title
        return MatchResult(path, status, candidate.score, candidate.source, summary)

    def _match_episode(self, path: Path,
                       by_source: dict[str, MetadataProvider]) -> MatchResult:
        parsed = parse_episode(path)
        if parsed is None:
            self.library.set_status(
                path, STATUS_UNMATCHED,
                _("Staffel/Episode im Dateinamen nicht erkennbar."))
            return MatchResult(path, STATUS_UNMATCHED)
        query = SearchQuery(kind=SERIES, title=parsed.series, year=parsed.year,
                           season=parsed.season, episode=parsed.episode)
        try:
            candidate, notes = identify(query, self.config, lambda: self._stop)
        except Exception as exc:  # noqa: BLE001
            self.library.set_status(path, STATUS_ERROR, str(exc))
            return MatchResult(path, STATUS_ERROR, detail=str(exc))
        if candidate is None:
            self.library.set_status(path, STATUS_UNMATCHED, notes)
            return MatchResult(path, STATUS_UNMATCHED, detail=notes)

        provider = by_source[candidate.source]
        info = provider.details(candidate)
        used = apply_supplements(info, query, self.config.providers)
        episode_info = _episode_details(
            provider, candidate.external_id, parsed.season, parsed.episode)
        # Kennt die Quelle die Episode nicht (z. B. ein Special, das TMDb
        # anders/gar nicht katalogisiert), lieber den Titel aus dem
        # Dateinamen nehmen als den Platz ganz leer zu lassen.
        episode_title = episode_info.title or parsed.guessed_title
        status = STATUS_MATCHED if candidate.score >= self.config.threshold \
            else STATUS_UNSURE
        note = "; ".join(filter(None, [
            notes, _("ergaenzt durch {sources}").format(
                sources=", ".join(used)) if used else ""]))
        self.library.set_match(
            path, info, candidate.score, status, season=parsed.season,
            episode=parsed.episode, episode_title=episode_title,
            episode_overview=episode_info.overview, note=note)
        summary = f"{info.title} S{parsed.season:02d}E{parsed.episode:02d}"
        return MatchResult(path, status, candidate.score, candidate.source, summary)


def run_in_thread(movie_paths: list[Path], episode_paths: list[Path],
                  config: MatchConfig, library: LibraryIndex):
    """Gibt (thread, worker) zurueck - der Aufrufer verbindet die Signale."""
    thread = QThread()
    worker = AutoMatchWorker(movie_paths, episode_paths, config, library)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    return thread, worker
