"""Poster-Thumbnails: Hintergrund-Download mit Cache auf der Platte."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import requests
from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QImage, QPixmap

THUMB_SIZE = 300


def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache")
    d = Path(base) / "moviedesk" / "posters"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_path(url: str) -> Path:
    return cache_dir() / (hashlib.sha1(url.encode()).hexdigest() + ".jpg")


class _Signals(QObject):
    done = Signal(str, QImage)


class _Job(QRunnable):
    def __init__(self, url: str, signals: _Signals):
        super().__init__()
        self.url = url
        self.signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:
        img = QImage()
        cache = _cache_path(self.url)
        if cache.exists():
            img.load(str(cache))
        if img.isNull():
            try:
                response = requests.get(self.url, timeout=15)
                response.raise_for_status()
                raw = QImage()
                raw.loadFromData(response.content)
                if not raw.isNull():
                    img = raw.scaledToWidth(THUMB_SIZE, Qt.SmoothTransformation)
                    img.save(str(cache), "JPG")
            except Exception:  # noqa: BLE001
                pass
        self.signals.done.emit(self.url, img)


class PosterLoader(QObject):
    """Laedt Poster nebenlaeufig und meldet sie per Signal."""

    ready = Signal(str, QPixmap)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(
            max(2, QThreadPool.globalInstance().maxThreadCount() - 1))
        self._signals = _Signals(self)
        self._signals.done.connect(self._on_done)
        self._pending: set[str] = set()
        self._cache: dict[str, QPixmap] = {}

    def get(self, url: str | None) -> QPixmap | None:
        if not url:
            return QPixmap()
        if url in self._cache:
            return self._cache[url]
        if url not in self._pending:
            self._pending.add(url)
            self._pool.start(_Job(url, self._signals))
        return None

    def clear_queue(self) -> None:
        self._pool.clear()
        self._pending.clear()

    def _on_done(self, url: str, img: QImage) -> None:
        self._pending.discard(url)
        pm = QPixmap.fromImage(img) if not img.isNull() else QPixmap()
        self._cache[url] = pm
        self.ready.emit(url, pm)
