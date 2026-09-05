"""Mehrere Episoden auf einmal einer anderen Serie zuordnen.

Die Serie selbst wird neu gewaehlt (Suche oder direkter TMDb-/IMDb-/
TheTVDB-Link), die Staffel-/Episodennummer jeder einzelnen Datei bleibt
unangetastet - nur die Episodentitel werden fuer die neue Serie nachgeladen.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QSize, Qt, QThread
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QTextBrowser, QVBoxLayout,
)

from .i18n import _
from .matcher import MatchConfig
from .matchdialog import _SearchWorker, resolve_reference, stop_search_thread
from .providers.base import Candidate, SearchQuery, SERIES
from .thumbs import PosterLoader

POSTER_W, ROW_H = 60, 88


class SeriesPickerDialog(QDialog):
    def __init__(self, config: MatchConfig, loader: PosterLoader,
                initial_title: str = "", parent=None):
        super().__init__(parent)
        self.config = config
        self.loader = loader
        self.loader.ready.connect(self._on_poster)
        self._thread: QObject | None = None

        self.setWindowTitle(_("Zu anderer Serie zuordnen …"))
        self.resize(560, 480)

        self.title_edit = QLineEdit(initial_title)
        search_button = QPushButton(_("Suchen"))
        search_button.clicked.connect(self.search)
        # Enter im Titelfeld soll suchen, nicht versehentlich den aktuell
        # markierten Treffer bestaetigen - siehe ok_button.setAutoDefault
        # weiter unten.
        self.title_edit.returnPressed.connect(self.search)
        search_row = QHBoxLayout()
        search_row.addWidget(self.title_edit, 1)
        search_row.addWidget(search_button)

        self.direct_edit = QLineEdit()
        self.direct_edit.setPlaceholderText(
            _("TMDb-, IMDb- oder TheTVDB-Episoden-Link/ID einfuegen - falls "
              "die Suche nichts findet"))
        direct_button = QPushButton(_("Laden"))
        direct_button.clicked.connect(self._load_direct)
        self.direct_edit.returnPressed.connect(self._load_direct)
        direct_row = QHBoxLayout()
        direct_row.addWidget(self.direct_edit, 1)
        direct_row.addWidget(direct_button)

        self.list = QListWidget()
        self.list.setIconSize(QSize(POSTER_W, ROW_H))
        self.list.itemSelectionChanged.connect(self._show_overview)

        self.overview = QTextBrowser()
        self.overview.setMaximumHeight(120)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.ok_button = buttons.button(QDialogButtonBox.Ok)
        self.ok_button.setEnabled(False)
        # Ohne das faengt der OK-Button per Qt-Vorgabe die Enter-Taste ab,
        # egal in welchem Feld man gerade tippt.
        self.ok_button.setAutoDefault(False)
        self.ok_button.setDefault(False)

        layout = QVBoxLayout(self)
        layout.addLayout(search_row)
        layout.addLayout(direct_row)
        layout.addWidget(self.list, 1)
        layout.addWidget(self.overview)
        layout.addWidget(buttons)

        if initial_title:
            self.search()

    def search(self) -> None:
        title = self.title_edit.text().strip()
        if not title:
            return
        self.list.clear()
        self.ok_button.setEnabled(False)
        query = SearchQuery(kind=SERIES, title=title)
        self._thread = QThread()
        worker = _SearchWorker(query, self.config)
        worker.moveToThread(self._thread)
        self._thread.started.connect(worker.run)
        worker.done.connect(self._on_results)
        worker.done.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)
        self._worker = worker
        self._thread.start()

    def _on_results(self, candidates: list[Candidate], notes: str) -> None:
        for candidate in candidates:
            year = f" ({candidate.year})" if candidate.year else ""
            list_item = QListWidgetItem(
                f"{candidate.title}{year}  ·  {candidate.source.upper()}")
            list_item.setData(Qt.UserRole, candidate)
            pm = self.loader.get(candidate.poster_url) if candidate.poster_url else None
            if pm and not pm.isNull():
                list_item.setIcon(pm)
            self.list.addItem(list_item)
        if not candidates and notes:
            self.overview.setPlainText(notes)
        if candidates:
            self.list.setCurrentRow(0)

    def _load_direct(self) -> None:
        text = self.direct_edit.text().strip()
        if not text:
            return
        try:
            info, kind, _season, _episode = resolve_reference(
                self.config, text, SERIES)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, _("TMDb-/IMDb-/TheTVDB-Link"), str(exc))
            return
        candidate = Candidate(
            source=info.source, external_id=info.external_id, kind=kind,
            title=info.title, year=info.year, overview=info.overview,
            poster_url=info.poster_url, rating=info.rating, score=100)

        self.list.clear()
        year = f" ({candidate.year})" if candidate.year else ""
        list_item = QListWidgetItem(
            f"{candidate.title}{year}  ·  manuell geladen ({info.source.upper()})")
        list_item.setData(Qt.UserRole, candidate)
        pm = self.loader.get(candidate.poster_url) if candidate.poster_url else None
        if pm and not pm.isNull():
            list_item.setIcon(pm)
        self.list.addItem(list_item)
        self.list.setCurrentRow(0)

    def done(self, result: int) -> None:  # noqa: N802 - Qt-Namenskonvention
        stop_search_thread(self._thread)
        super().done(result)

    def _on_poster(self, url: str, pixmap) -> None:
        for row in range(self.list.count()):
            item = self.list.item(row)
            candidate: Candidate = item.data(Qt.UserRole)
            if candidate.poster_url == url and not pixmap.isNull():
                item.setIcon(pixmap)

    def _show_overview(self) -> None:
        items = self.list.selectedItems()
        self.ok_button.setEnabled(bool(items))
        if items:
            candidate: Candidate = items[0].data(Qt.UserRole)
            self.overview.setPlainText(candidate.overview)

    def selected_candidate(self) -> Candidate | None:
        items = self.list.selectedItems()
        return items[0].data(Qt.UserRole) if items else None
