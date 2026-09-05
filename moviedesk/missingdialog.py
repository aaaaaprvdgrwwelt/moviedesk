"""Gesamtuebersicht: fehlende Filme (alle Sammlungen) und fehlende Episoden
(alle Serien) auf einen Blick - optional gefiltert auf bereits
veroeffentlichte/ausgestrahlte Teile."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QObject, QThread, Signal, Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
)

from .i18n import _
from .library import LibraryIndex
from .providers.base import MissingEpisode, MissingMovie

MOVIE_ROLE = Qt.UserRole
SERIES_ROLE = Qt.UserRole + 1


class MissingScanWorker(QObject):
    """Fragt TMDb fuer jede bekannte Sammlung/Serie ab, was fehlt - laeuft in
    einem eigenen Thread, da das viele Netzwerkaufrufe sein koennen."""

    progress = Signal(str)
    finished = Signal(list, list)  # [(sammlung, [MissingMovie])], [(serie, [MissingEpisode])]

    def __init__(self, library: LibraryIndex, provider, only_released: bool,
                country: str):
        super().__init__()
        self.library = library
        self.provider = provider
        self.only_released = only_released
        self.country = country

    def run(self) -> None:
        today = date.today().isoformat()
        movies_result: list[tuple[str, list[MissingMovie]]] = []
        for name, _count in self.library.collections():
            self.progress.emit(name)
            owned = self.library.list_movies(name)
            collection_id = next(
                (m.collection_id for m in owned
                 if m.source == "tmdb" and m.collection_id), "")
            if not collection_id:
                continue
            try:
                all_movies = self.provider.collection_movies(
                    collection_id, self.country if self.only_released else "")
            except Exception:  # noqa: BLE001
                continue
            owned_ids = {m.external_id for m in owned if m.source == "tmdb"}
            missing = [m for m in all_movies if m.tmdb_id not in owned_ids]
            if self.only_released:
                missing = [m for m in missing
                          if m.release_date and m.release_date[:10] <= today]
            if missing:
                movies_result.append((name, missing))

        episodes_result: list[tuple[str, list[MissingEpisode]]] = []
        for title, episodes in self.library.series_groups():
            self.progress.emit(title)
            series_id = next(
                (e.external_id for e in episodes
                 if e.source == "tmdb" and e.external_id), "")
            if not series_id:
                continue
            try:
                roster = self.provider.series_roster(series_id)
            except Exception:  # noqa: BLE001
                continue
            owned_pairs = {(e.season, e.episode) for e in episodes}
            missing = [e for e in roster if (e.season, e.episode) not in owned_pairs]
            if self.only_released:
                missing = [e for e in missing
                          if e.air_date and e.air_date[:10] <= today]
            if missing:
                episodes_result.append((title, missing))

        self.finished.emit(movies_result, episodes_result)


def run_in_thread(library: LibraryIndex, provider, only_released: bool, country: str):
    """Gibt (thread, worker) zurueck - der Aufrufer verbindet die Signale."""
    thread = QThread()
    worker = MissingScanWorker(library, provider, only_released, country)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    return thread, worker


class MissingOverviewDialog(QDialog):
    """Zeigt das Ergebnis eines `MissingScanWorker`-Laufs an. Ein Doppelklick
    auf einen Sammlungs-/Serien-Knoten merkt sich dessen Namen in
    `jump_to` - der Aufrufer kann danach dorthin springen."""

    def __init__(self, only_released: bool, country: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Fehlende Teile"))
        self.resize(560, 640)
        self.jump_to_collection: str | None = None
        self.jump_to_series: str | None = None

        self.status_label = QLabel(_("Suche fehlende Teile …"))
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemDoubleClicked.connect(self._on_double_click)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(self.status_label)
        layout.addWidget(self.tree)
        layout.addWidget(buttons)

    def set_progress(self, text: str) -> None:
        self.status_label.setText(text)

    def show_results(self, movies: list[tuple[str, list[MissingMovie]]],
                     episodes: list[tuple[str, list[MissingEpisode]]]) -> None:
        self.tree.clear()
        if not movies and not episodes:
            self.status_label.setText(_("Nichts fehlt - vollstaendig."))
            return

        total = sum(len(m) for _n, m in movies) + sum(len(e) for _n, e in episodes)
        self.status_label.setText(
            _("{n} fehlende Teile - Doppelklick springt zur Sammlung/Serie.")
            .format(n=total))

        if movies:
            movies_root = QTreeWidgetItem(self.tree, [_("Filme")])
            movies_root.setExpanded(True)
            for name, missing in movies:
                node = QTreeWidgetItem(
                    movies_root, [f"{name}  ({len(missing)})"])
                node.setData(0, MOVIE_ROLE, name)
                node.setExpanded(True)
                for movie in sorted(missing, key=lambda m: m.release_date or ""):
                    year = f" ({movie.year})" if movie.year else ""
                    date_suffix = f"  -  {movie.release_date}" if movie.release_date else ""
                    child = QTreeWidgetItem(node, [f"{movie.title}{year}{date_suffix}"])
                    child.setData(0, MOVIE_ROLE, name)

        if episodes:
            episodes_root = QTreeWidgetItem(self.tree, [_("Serien")])
            episodes_root.setExpanded(True)
            for title, missing in episodes:
                node = QTreeWidgetItem(
                    episodes_root, [f"{title}  ({len(missing)})"])
                node.setData(0, SERIES_ROLE, title)
                node.setExpanded(True)
                for ep in sorted(missing, key=lambda e: (e.season, e.episode)):
                    tag = f"S{ep.season:02d}E{ep.episode:02d}"
                    date_suffix = f"  -  {ep.air_date}" if ep.air_date else ""
                    child = QTreeWidgetItem(
                        node, [f"{tag}  {ep.title}{date_suffix}"])
                    child.setData(0, SERIES_ROLE, title)

    def _on_double_click(self, item: QTreeWidgetItem, _column: int) -> None:
        collection = item.data(0, MOVIE_ROLE)
        series = item.data(0, SERIES_ROLE)
        if collection:
            self.jump_to_collection = collection
            self.accept()
        elif series:
            self.jump_to_series = series
            self.accept()
