"""Bibliotheksordner einlesen: Videodateien finden, Samples aussortieren."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from .library import EPISODE, LibraryIndex, MOVIE
from .parser import VIDEO_EXTENSIONS, is_sample_or_extra, parse_episode, parse_movie


def find_videos(root: Path) -> list[Path]:
    """Alle Videodateien unter `root`, ohne offensichtliche Samples/Extras."""
    if not root.is_dir():
        return []
    found: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        if is_sample_or_extra(path.stem):
            continue
        found.append(path)
    found.sort(key=lambda p: str(p).casefold())
    return found


class ScanWorker(QObject):
    """Laeuft im eigenen Thread - Verzeichnisse koennen gross sein, die
    Oberflaeche soll dabei nicht einfrieren."""

    progress = Signal(str)   # aktuell durchsuchter Ordner
    finished = Signal()

    def __init__(self, movie_roots: list[str], series_roots: list[str],
                library: LibraryIndex):
        super().__init__()
        self.movie_roots = movie_roots
        self.series_roots = series_roots
        self.library = library
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        for root in self.movie_roots:
            if self._stop:
                break
            self.progress.emit(root)
            root_path = Path(root)
            found = find_videos(root_path)
            for path in found:
                if self._stop:
                    break
                parsed = parse_movie(path)
                self.library.mark_scanned(
                    path, MOVIE, root_path, parsed.title, parsed.year)
            # find_videos() lief vollstaendig, auch bei einem Abbruch mitten
            # in der Schleife darueber - das Aufraeumen bleibt deshalb sicher
            # auf tatsaechlich fehlende Dateien beschraenkt.
            self.library.forget_missing(root_path, {str(p) for p in found})
        for root in self.series_roots:
            if self._stop:
                break
            self.progress.emit(root)
            root_path = Path(root)
            found = find_videos(root_path)
            for path in found:
                if self._stop:
                    break
                parsed = parse_episode(path)
                if parsed is None:
                    self.library.mark_scanned(path, EPISODE, root_path)
                    continue
                self.library.mark_scanned(
                    path, EPISODE, root_path, parsed.series, parsed.year,
                    parsed.season, parsed.episode, parsed.episode_end)
            self.library.forget_missing(root_path, {str(p) for p in found})
        self.finished.emit()


def run_in_thread(movie_roots: list[str], series_roots: list[str],
                  library: LibraryIndex):
    """Gibt (thread, worker) zurueck - der Aufrufer verbindet die Signale."""
    thread = QThread()
    worker = ScanWorker(movie_roots, series_roots, library)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    return thread, worker


def scan_folder(folder: Path, root: Path, kind: str, library: LibraryIndex,
                should_stop=None) -> None:
    """Nur `folder` neu einlesen - z. B. der Unterordner einer einzelnen
    Serie oder eines einzelnen Films, statt des ganzen Wurzelordners `root`.
    Eintraege werden weiterhin unter `root` gefuehrt (wie beim vollen Scan),
    aber nur unterhalb von `folder` verglichen/aufgeraeumt. `should_stop`
    ist ein parameterloses Callable, das True liefert, sobald abgebrochen
    werden soll (siehe FolderScanWorker.stop())."""
    should_stop = should_stop or (lambda: False)
    found = find_videos(folder)
    for path in found:
        if should_stop():
            break
        if kind == MOVIE:
            parsed = parse_movie(path)
            library.mark_scanned(path, MOVIE, root, parsed.title, parsed.year)
        else:
            parsed = parse_episode(path)
            if parsed is None:
                library.mark_scanned(path, EPISODE, root)
                continue
            library.mark_scanned(
                path, EPISODE, root, parsed.series, parsed.year,
                parsed.season, parsed.episode, parsed.episode_end)
    library.forget_missing_under(folder, {str(p) for p in found})


class FolderScanWorker(QObject):
    """Wie `ScanWorker`, aber fuer einen einzelnen Unterordner statt aller
    konfigurierten Wurzelordner - fuer den gezielten Scan aus dem
    Kontextmenue einer einzelnen Serie oder eines einzelnen Films."""

    progress = Signal(str)
    finished = Signal()

    def __init__(self, folder: Path, root: Path, kind: str, library: LibraryIndex):
        super().__init__()
        self.folder = folder
        self.root = root
        self.kind = kind
        self.library = library
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        self.progress.emit(str(self.folder))
        scan_folder(self.folder, self.root, self.kind, self.library,
                   should_stop=lambda: self._stop)
        self.finished.emit()


def run_folder_in_thread(folder: Path, root: Path, kind: str, library: LibraryIndex):
    """Gibt (thread, worker) zurueck - der Aufrufer verbindet die Signale."""
    thread = QThread()
    worker = FolderScanWorker(folder, root, kind, library)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    return thread, worker
