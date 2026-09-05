"""Poster-Thumbnails: Hintergrund-Download mit Cache auf der Platte."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import requests
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap

from deskkit.thumbs import ThumbLoader as _ThumbLoader

THUMB_SIZE = 300


def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache")
    d = Path(base) / "moviedesk" / "posters"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_path(url: str) -> Path:
    return cache_dir() / (hashlib.sha1(url.encode()).hexdigest() + ".jpg")


def _load(url: str) -> QImage:
    img = QImage()
    cache = _cache_path(url)
    if cache.exists():
        img.load(str(cache))
    if img.isNull():
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            raw = QImage()
            raw.loadFromData(response.content)
            if not raw.isNull():
                img = raw.scaledToWidth(THUMB_SIZE, Qt.SmoothTransformation)
                img.save(str(cache), "JPG")
        except Exception:  # noqa: BLE001
            pass
    return img


class PosterLoader(_ThumbLoader):
    """Laedt Poster nebenlaeufig und meldet sie per Signal."""

    def __init__(self, parent=None):
        super().__init__(_load, parent)

    def get(self, url: str | None) -> QPixmap | None:
        if not url:
            return QPixmap()
        return super().get(url)
