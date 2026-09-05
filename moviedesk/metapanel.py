"""Detailanzeige: Poster plus Metadaten des ausgewaehlten Eintrags."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QLabel, QPlainTextEdit, QSizePolicy, QVBoxLayout, QWidget,
)

from .i18n import _
from .library import EPISODE, Item
from .thumbs import PosterLoader

POSTER_W = 220

SOURCE_NAMES = {"tmdb": "TMDb", "tvdb": "TheTVDB", "omdb": "OMDb"}


class MetaPanel(QWidget):
    def __init__(self, loader: PosterLoader, parent=None):
        super().__init__(parent)
        self._loader = loader
        self._loader.ready.connect(self._on_poster)
        self._url = ""

        self.poster = QLabel()
        self.poster.setFixedWidth(POSTER_W)
        self.poster.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self.poster.setStyleSheet("border-radius: 6px;")

        self.title = QLabel()
        self.title.setWordWrap(True)
        font = self.title.font()
        font.setPointSize(font.pointSize() + 3)
        font.setBold(True)
        self.title.setFont(font)

        self.subtitle = QLabel()
        self.subtitle.setWordWrap(True)

        self.overview = QPlainTextEdit()
        self.overview.setReadOnly(True)
        self.overview.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        self.source_label = QLabel()
        self.source_label.setOpenExternalLinks(True)
        self.source_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.source_label.setStyleSheet("font-size: 90%;")

        self.path_label = QLabel()
        self.path_label.setWordWrap(True)
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.path_label.setStyleSheet("color: palette(mid); font-size: 90%;")

        layout = QVBoxLayout(self)
        layout.addWidget(self.poster, 0, Qt.AlignHCenter)
        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)
        layout.addWidget(self.overview, 1)
        layout.addWidget(self.source_label)
        layout.addWidget(self.path_label)
        self.clear()

    def clear(self) -> None:
        self.poster.setPixmap(QPixmap())
        self.title.setText(_("Kein Eintrag ausgewaehlt"))
        self.subtitle.setText("")
        self.overview.setPlainText("")
        self.source_label.setText("")
        self.path_label.setText("")
        self._url = ""

    def show_item(self, item: Item | None) -> None:
        if item is None:
            self.clear()
            return
        self.title.setText(item.title or _("(ohne Titel)"))

        bits: list[str] = []
        if item.kind == EPISODE and item.season is not None and item.episode is not None:
            bits.append(f"S{item.season:02d}E{item.episode:02d}")
            if item.episode_title:
                bits.append(item.episode_title)
        elif item.year:
            bits.append(str(item.year))
        if item.genres:
            bits.append(", ".join(item.genres))
        if item.rating:
            bits.append(f"★ {item.rating:.1f}")
        self.subtitle.setText(" · ".join(bits))
        plot = (item.episode_overview if item.kind == EPISODE else "") or item.overview
        self.overview.setPlainText(plot)

        if item.source:
            name = SOURCE_NAMES.get(item.source, item.source.upper())
            url = item.source_url
            if url:
                self.source_label.setText(
                    _('Quelle: <a href="{url}">{name} ansehen ↗</a>').format(
                        url=url, name=name))
            else:
                self.source_label.setText(_("Quelle: {name}").format(name=name))
        else:
            self.source_label.setText("")

        self.path_label.setText(item.path)
        self.path_label.setToolTip(item.path)

        self._url = item.poster_url or ""
        pm = self._loader.get(self._url) if self._url else QPixmap()
        self._apply_poster(pm)

    def _on_poster(self, url: str, pixmap: QPixmap) -> None:
        if url == self._url:
            self._apply_poster(pixmap)

    def _apply_poster(self, pixmap: QPixmap | None) -> None:
        if pixmap and not pixmap.isNull():
            self.poster.setPixmap(
                pixmap.scaledToWidth(POSTER_W, Qt.SmoothTransformation))
        else:
            self.poster.setPixmap(QPixmap())
