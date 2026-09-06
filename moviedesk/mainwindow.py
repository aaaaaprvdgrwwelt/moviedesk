"""Hauptfenster: Filme/Serien-Raster, Scan, Zuordnung, Umbenennen."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMenu, QMessageBox, QProgressDialog, QPushButton, QSizePolicy,
    QSplitter, QStatusBar, QTableWidget,
    QTableWidgetItem, QTabWidget, QToolBar, QToolButton, QVBoxLayout, QWidget,
)
from send2trash import send2trash

from deskkit.actions import ActionRegistry
from deskkit.paths import subfolder_of
from deskkit.tiles import STATUS_ROLE, SUBTITLE_ROLE, CoverDelegate, configure_grid

from . import missingdialog, nfo, renamer, scanner, subtitles
from .appicon import icon as app_icon
from .config import Settings
from .helpdialog import HelpDialog
from .i18n import _, set_language
from .icons import icon as tool_icon
from .library import EPISODE, Item, LibraryIndex, MOVIE as LIB_MOVIE, STATUS_MATCHED
from .matcher import run_in_thread
from .matchdialog import MatchDialog
from .metapanel import MetaPanel
from .renamedialog import RenameDialog
from .seriespicker import SeriesPickerDialog
from .settingsdialog import SettingsDialog
from .thumbs import PosterLoader

TILE_W = 140
POSTER_H = 205


STATUS_LABEL = {
    "matched": _("zugeordnet"),
    "unsure": _("unsicher"),
    "unmatched": _("nicht zugeordnet"),
    "error": _("Fehler"),
    "missing": _("fehlt in der Sammlung"),
}

STATUS_COLOR = {
    "matched": QColor(46, 160, 90),
    "unsure": QColor(214, 154, 40),
    "unmatched": QColor(150, 150, 150),
    "error": QColor(192, 57, 43),
    "missing": QColor(120, 120, 120),
}

#: Kennzeichnet eine nur angezeigte (nicht besessene) Kachel bei "Fehlende
#: Filme/Episoden pruefen" - id -1 gibt es in der Datenbank nie.
MISSING_ID = -1


class _SeasonPickerDialog(QDialog):
    """Staffel anhand ihrer tatsaechlichen Episodentitel auswaehlen, statt
    eine Nummer zu raten - siehe MainWindow._reassign_season()."""

    def __init__(self, roster: list, current_season: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Staffel waehlen"))
        self.resize(420, 440)
        self._roster = roster

        seasons = sorted({e.season for e in roster})
        self.combo = QComboBox()
        for season in seasons:
            count = sum(1 for e in roster if e.season == season)
            self.combo.addItem(
                _("Staffel {s} ({n} Episoden)").format(s=season, n=count), season)
        index = self.combo.findData(current_season)
        self.combo.setCurrentIndex(index if index >= 0 else 0)
        self.combo.currentIndexChanged.connect(self._update_preview)

        self.preview = QListWidget()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(_("Staffel:")))
        layout.addWidget(self.combo)
        layout.addWidget(QLabel(_("Episoden dieser Staffel - zur Kontrolle, "
                                  "ob es die richtige ist:")))
        layout.addWidget(self.preview, 1)
        layout.addWidget(buttons)
        self._update_preview()

    def _update_preview(self) -> None:
        self.preview.clear()
        season = self.combo.currentData()
        episodes = sorted((e for e in self._roster if e.season == season),
                          key=lambda e: e.episode)
        for episode in episodes:
            self.preview.addItem(f"E{episode.episode:02d}  {episode.title}")

    def selected_season(self) -> int:
        return self.combo.currentData()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MovieDesk")
        self.setWindowIcon(app_icon())
        self.resize(1200, 760)

        self.qsettings = QSettings("moviedesk", "moviedesk")
        self.settings = Settings.load(self.qsettings)
        set_language(self.settings.language)

        self.library = LibraryIndex()
        self.loader = PosterLoader(self)
        self.loader.ready.connect(self._on_poster)

        self._search_text = ""
        self._build_central()
        self._build_actions()
        self._build_toolbar()
        self._build_menubar()
        self.setStatusBar(QStatusBar())

        self._series_items: dict[str, list[Item]] = {}
        self.refresh_view()

    # ------------------------------------------------------------------
    def _build_actions(self) -> None:
        """Eine QAction je Kommando - von Menue, Werkzeugleiste und
        Kontextmenues gemeinsam benutzt (siehe deskkit.actions)."""
        self.actions_map = ActionRegistry(self, _)
        a = self.actions_map
        a.add("add_movie_root", "Filme-Ordner …", slot=self._add_movie_root)
        a.add("add_series_root", "Serien-Ordner …", slot=self._add_series_root)
        a.add("scan", "Scannen", "F5", self.scan_all, tool_icon("refresh"))
        a.add("auto_match", "Automatisch zuordnen", "Ctrl+T", self.auto_match,
             tool_icon("match"))
        a.add("missing", "Fehlende Teile …", "Ctrl+M", self.show_missing_overview,
             tool_icon("warn"))
        a.add("rename", "Umbenennen …", "Ctrl+R", self.rename_preview,
             tool_icon("rename"))
        a.add("nfo", "NFO erzeugen (Kodi/Jellyfin)", None, self.write_nfo_files,
             tool_icon("nfo"))
        a.add("subtitles", "Untertitel herunterladen …", None,
             self.download_subtitles, tool_icon("subtitle"))
        # Ziel self.tabs statt Fenster: sonst friesst "Entf" im Suchfeld
        # Zeichen statt normal Text zu loeschen.
        a.add("delete", "Loeschen …", "Del", self.delete_selected,
             tool_icon("delete"), target=self.tabs,
             shortcut_context=Qt.WidgetWithChildrenShortcut)
        a.add("search", "Suchen", "Ctrl+F", self.focus_search)
        a.add("backup", "Bibliothek sichern …", None, self.backup_library)
        a.add("settings", "Einstellungen …", "Ctrl+,", self.open_settings,
             tool_icon("settings"))
        a.add("help", "Hilfe …", "F1", self.open_help, tool_icon("help"))
        a.add("quit", "Beenden", "Ctrl+Q", self.close)

    def _build_toolbar(self) -> None:
        bar = QToolBar()
        bar.setMovable(False)
        bar.setIconSize(QSize(20, 20))
        self.addToolBar(bar)
        a = self.actions_map

        add_action = bar.addAction(tool_icon("folder_new"), _("Ordner hinzufuegen …"))
        menu = QMenu(self)
        menu.addAction(a["add_movie_root"])
        menu.addAction(a["add_series_root"])
        add_action.setMenu(menu)
        # Klick auf den Knopf soll dasselbe Menue oeffnen wie der Pfeil.
        button = bar.widgetForAction(add_action)
        if isinstance(button, QToolButton):
            button.setPopupMode(QToolButton.InstantPopup)

        bar.addAction(a["scan"])
        bar.addAction(a["auto_match"])
        bar.addAction(a["missing"])
        bar.addSeparator()
        bar.addAction(a["rename"])
        bar.addAction(a["nfo"])
        bar.addAction(a["subtitles"])
        bar.addAction(a["delete"])
        bar.addSeparator()
        bar.addAction(a["settings"])
        bar.addAction(a["help"])

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        bar.addWidget(spacer)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(_("Suchen …"))
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMaximumWidth(240)
        self.search_edit.textChanged.connect(self._on_search_changed)
        bar.addWidget(self.search_edit)

    def _build_menubar(self) -> None:
        a = self.actions_map
        bar = self.menuBar()

        menu = bar.addMenu(_("&Datei"))
        menu.addAction(a["add_movie_root"])
        menu.addAction(a["add_series_root"])
        menu.addSeparator()
        menu.addAction(a["scan"])
        menu.addSeparator()
        menu.addAction(a["backup"])
        menu.addSeparator()
        menu.addAction(a["quit"])

        menu = bar.addMenu(_("&Bearbeiten"))
        menu.addAction(a["rename"])
        menu.addAction(a["delete"])

        menu = bar.addMenu(_("&Ansicht"))
        menu.addAction(a["search"])
        menu.addAction(a["missing"])

        menu = bar.addMenu(_("E&xtras"))
        menu.addAction(a["auto_match"])
        menu.addAction(a["nfo"])
        menu.addAction(a["subtitles"])
        menu.addSeparator()
        menu.addAction(a["settings"])

        bar.addMenu(_("&Hilfe")).addAction(a["help"])

    def focus_search(self) -> None:
        self.search_edit.selectAll()
        self.search_edit.setFocus()

    def _build_central(self) -> None:
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # --- Filme --------------------------------------------------
        self.collection_list = QListWidget()
        self.collection_list.itemSelectionChanged.connect(self._on_collection_selected)
        self.missing_movies_button = QPushButton(_("Fehlende Filme aktualisieren"))
        self.missing_movies_button.setEnabled(False)
        self.missing_movies_button.clicked.connect(self._refresh_missing_movies)
        collection_panel = QWidget()
        collection_layout = QVBoxLayout(collection_panel)
        collection_layout.setContentsMargins(0, 0, 0, 0)
        collection_layout.addWidget(self.collection_list)
        collection_layout.addWidget(self.missing_movies_button)

        self.movie_list = QListWidget()
        self._configure_grid(self.movie_list)
        self.movie_list.itemSelectionChanged.connect(self._on_movie_selected)
        self.movie_list.itemDoubleClicked.connect(
            lambda _i: self._play(self._current_movie()))
        self.movie_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.movie_list.customContextMenuRequested.connect(self._movie_context_menu)

        self.movie_meta = MetaPanel(self.loader)
        movie_split = QSplitter()
        movie_split.addWidget(collection_panel)
        movie_split.addWidget(self.movie_list)
        movie_split.addWidget(self.movie_meta)
        movie_split.setStretchFactor(0, 1)
        movie_split.setStretchFactor(1, 3)
        movie_split.setStretchFactor(2, 2)
        self.tabs.addTab(movie_split, tool_icon("movie"), _("Filme"))

        # --- Serien ---------------------------------------------------
        self.series_list = QListWidget()
        self._configure_grid(self.series_list)
        self.series_list.itemSelectionChanged.connect(self._on_series_selected)
        self.series_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.series_list.customContextMenuRequested.connect(self._series_context_menu)
        self.missing_episodes_button = QPushButton(_("Fehlende Episoden aktualisieren"))
        self.missing_episodes_button.setEnabled(False)
        self.missing_episodes_button.clicked.connect(self._refresh_missing_episodes)
        series_panel = QWidget()
        series_panel_layout = QVBoxLayout(series_panel)
        series_panel_layout.setContentsMargins(0, 0, 0, 0)
        series_panel_layout.addWidget(self.series_list)
        series_panel_layout.addWidget(self.missing_episodes_button)

        self.episode_table = QTableWidget(0, 4)
        self.episode_table.setHorizontalHeaderLabels(
            [_("Episode"), _("Titel"), _("Datei"), _("Status")])
        # Interactive statt Stretch fuer alle Spalten - sonst laesst sich die
        # Breite per Maus nicht mehr veraendern. Die Anfangsbreiten kommen
        # aus resizeColumnsToContents() beim Befuellen (_fill_episode_table).
        header = self.episode_table.horizontalHeader()
        for column in range(4):
            header.setSectionResizeMode(column, QHeaderView.Interactive)
        # Klick auf eine Spaltenueberschrift sortiert danach (z. B. nach
        # Datei). Beim Befuellen (_fill_episode_table/_check_missing_episodes)
        # wird das kurz abgeschaltet - sonst sortiert Qt schon waehrend eine
        # Zeile erst teilweise gefuellt ist.
        self.episode_table.setSortingEnabled(True)
        self.episode_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.episode_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.episode_table.itemSelectionChanged.connect(self._on_episode_selected)
        self.episode_table.itemDoubleClicked.connect(
            lambda _i: self._play(self._current_episode()))
        self.episode_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.episode_table.customContextMenuRequested.connect(
            self._episode_context_menu)

        self.series_meta = MetaPanel(self.loader)
        series_split = QSplitter()
        series_split.addWidget(series_panel)
        series_split.addWidget(self.episode_table)
        series_split.addWidget(self.series_meta)
        series_split.setStretchFactor(0, 2)
        series_split.setStretchFactor(1, 3)
        series_split.setStretchFactor(2, 2)
        self.tabs.addTab(series_split, tool_icon("tv"), _("Serien"))

    def _configure_grid(self, widget: QListWidget) -> None:
        configure_grid(widget, CoverDelegate(
            STATUS_COLOR, tile_w=TILE_W, cover_h=POSTER_H, parent=widget))

    # --- Ordner verwalten -----------------------------------------------
    def _add_movie_root(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, _("Ordner waehlen"))
        if not folder:
            return
        self.settings.movie_roots.append(folder)
        self.settings.save(self.qsettings)
        self.scan_all()

    def _add_series_root(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, _("Ordner waehlen"))
        if not folder:
            return
        self.settings.series_roots.append(folder)
        self.settings.save(self.qsettings)
        self.scan_all()

    # --- Scannen -----------------------------------------------------
    def _scan_target(self, folder: Path, root: Path, kind: str) -> None:
        """Nur `folder` neu einlesen - fuer den gezielten Scan einer
        einzelnen Serie oder eines einzelnen Films aus dem Kontextmenue,
        statt jedes Mal den ganzen Wurzelordner zu durchsuchen."""
        progress = QProgressDialog(_("Scanne …"), _("Abbrechen"), 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)

        thread, worker = scanner.run_folder_in_thread(folder, root, kind, self.library)
        worker.progress.connect(progress.setLabelText)
        progress.canceled.connect(worker.stop)
        thread.finished.connect(progress.close)
        thread.finished.connect(self.refresh_view)
        thread.finished.connect(
            lambda: self.statusBar().showMessage(_("Scan abgeschlossen."), 4000))
        self._scan_thread, self._scan_worker = thread, worker
        thread.start()
        progress.exec()
        thread.wait(5000)

    def _scan_series(self, title: str) -> None:
        episodes = [e for e in self.library.list_episodes() if e.title == title]
        if not episodes:
            return
        root = Path(episodes[0].root)
        self._scan_target(subfolder_of(Path(episodes[0].path), root), root, EPISODE)

    def _scan_movie(self, movie: Item) -> None:
        root = Path(movie.root)
        self._scan_target(subfolder_of(Path(movie.path), root), root, LIB_MOVIE)

    def scan_all(self) -> None:
        if not self.settings.movie_roots and not self.settings.series_roots:
            QMessageBox.information(
                self, _("Scannen"), _("Bitte mindestens einen Ordner hinzufuegen."))
            return

        progress = QProgressDialog(_("Scanne …"), _("Abbrechen"), 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)

        thread, worker = scanner.run_in_thread(
            self.settings.movie_roots, self.settings.series_roots, self.library)
        worker.progress.connect(progress.setLabelText)
        progress.canceled.connect(worker.stop)
        thread.finished.connect(progress.close)
        thread.finished.connect(self.refresh_view)
        thread.finished.connect(
            lambda: self.statusBar().showMessage(_("Scan abgeschlossen."), 4000))
        self._scan_thread, self._scan_worker = thread, worker
        thread.start()
        progress.exec()
        # Egal wie der Dialog geschlossen wurde (normal oder erzwungen) -
        # erst weiter, wenn der Thread wirklich fertig ist. Sonst droht ein
        # Absturz, wenn Qt-Objekte aus dem falschen Thread zerstoert werden.
        thread.wait(5000)

    # --- Automatisches Zuordnen ---------------------------------------
    def auto_match(self) -> None:
        config = self.settings.build_config()
        if not config.providers:
            QMessageBox.warning(
                self, _("Automatisch zuordnen"),
                _("Kein API-Key hinterlegt.") + " " + _("Einstellungen …"))
            return
        selected_movies = self._selected_movies()
        selected_episodes = self._selected_episodes()
        if selected_movies or selected_episodes:
            # Nur die markierten Eintraege - unabhaengig vom Status, damit
            # sich auch ein bereits zugeordneter Film gezielt neu abgleichen
            # laesst.
            movie_paths = [Path(i.path) for i in selected_movies]
            episode_paths = [Path(i.path) for i in selected_episodes]
        else:
            pending = self.library.unresolved()
            movie_paths = [Path(i.path) for i in pending if i.kind == LIB_MOVIE]
            episode_paths = [Path(i.path) for i in pending if i.kind == EPISODE]
        if not movie_paths and not episode_paths:
            QMessageBox.information(
                self, _("Automatisch zuordnen"),
                _("Nichts zu tun - alles bereits zugeordnet."))
            return

        total = len(movie_paths) + len(episode_paths)
        progress = QProgressDialog(_("Ordne zu …"), _("Abbrechen"), 0, total, self)
        progress.setWindowModality(Qt.WindowModal)
        # Ohne das wuerde die Anzeige sich schon beim letzten Element schliessen -
        # der Fortschritt wird vor der eigentlichen Arbeit an diesem Element
        # gemeldet, dann waere value==maximum, bevor wirklich alles fertig ist.
        progress.setAutoClose(False)
        progress.setAutoReset(False)

        thread, worker = run_in_thread(movie_paths, episode_paths, config, self.library)
        worker.progress.connect(lambda i, n, name: (
            progress.setMaximum(n), progress.setValue(i), progress.setLabelText(name)))
        progress.canceled.connect(worker.stop)
        thread.finished.connect(progress.close)
        thread.finished.connect(self.refresh_view)
        self._match_thread, self._match_worker = thread, worker
        thread.start()
        progress.exec()
        thread.wait(5000)

    # --- Manuelles Zuordnen -----------------------------------------
    def _play(self, item: Item | None) -> None:
        """Startet die Videodatei mit dem beim Betriebssystem hinterlegten
        Standardprogramm - kein eigener Player, das machen VLC/mpv/etc.
        zuverlaessiger."""
        if item is None or not item.path:
            return
        path = Path(item.path)
        if not path.exists():
            QMessageBox.warning(
                self, _("Abspielen"),
                _("Datei nicht gefunden - eventuell verschoben oder geloescht."))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _manual_match(self, item: Item | None) -> None:
        if item is None:
            return
        config = self.settings.build_config()
        if not config.providers:
            QMessageBox.warning(
                self, _("Automatisch zuordnen"), _("Kein API-Key hinterlegt."))
            return
        dialog = MatchDialog(item, config, self.library, self.loader, self)
        if dialog.exec():
            self.refresh_view()

    def _reassign_season(self, episodes: list[Item]) -> None:
        """Mehrere Episoden auf einmal einer anderen Staffel zuordnen - z. B.
        wenn der Dateiname/Ordner beim Scan die falsche Staffel ergeben hat.
        Die Episodennummer bleibt je Datei erhalten, nur die Staffel aendert
        sich; der passende Episodentitel wird dafuer neu geladen."""
        candidates = [e for e in episodes if e.source and e.external_id]
        if not candidates:
            QMessageBox.warning(
                self, _("Zu anderer Staffel zuordnen …"),
                _("Diese Episode(n) sind noch keiner Serie zugeordnet - "
                  "erst automatisch oder manuell zuordnen."))
            return
        reference = candidates[0]
        providers = {p.name: p for p in self.settings.build_providers()}
        provider = providers.get(reference.source)
        if provider is None:
            QMessageBox.warning(
                self, _("Zu anderer Staffel zuordnen …"),
                _("Kein API-Key hinterlegt."))
            return
        try:
            roster = provider.series_roster(reference.external_id)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, _("Zu anderer Staffel zuordnen …"), str(exc))
            return
        if not roster:
            QMessageBox.warning(
                self, _("Zu anderer Staffel zuordnen …"),
                _("Konnte die Staffelliste dieser Serie nicht laden."))
            return

        picker = _SeasonPickerDialog(roster, reference.season or 0, self)
        if not picker.exec():
            return
        new_season = picker.selected_season()

        updated, skipped = 0, 0
        for item in episodes:
            if item.episode is None or not item.source or not item.external_id:
                skipped += 1
                continue
            episode_title, episode_overview = "", ""
            item_provider = providers.get(item.source)
            if item_provider is not None:
                try:
                    ep_info = item_provider.episode(
                        item.external_id, new_season, item.episode)
                    if ep_info:
                        episode_title = ep_info.title
                        episode_overview = ep_info.overview
                except Exception:  # noqa: BLE001
                    pass
            self.library.reassign_episode(
                Path(item.path), new_season, item.episode, episode_title,
                episode_overview, note=_("Staffel von Hand geaendert"))
            updated += 1

        self.refresh_view()
        message = _("{n} Episode(n) auf Staffel {s} gesetzt.").format(
            n=updated, s=new_season)
        if skipped:
            message += " " + _(
                "{n} uebersprungen (noch keiner Serie zugeordnet)."
            ).format(n=skipped)
        QMessageBox.information(self, _("Zu anderer Staffel zuordnen …"), message)

    def _reassign_series(self, episodes: list[Item]) -> None:
        """Mehrere Episoden auf einmal einer komplett anderen Serie zuordnen.

        Im Unterschied zu `_reassign_season` bleibt hier die Staffel-/
        Episodennummer jeder einzelnen Datei unangetastet - nur die Serie
        selbst (und damit Titel/Poster/Beschreibung sowie die passenden
        Episodentitel) wird ausgetauscht."""
        if not episodes:
            return
        config = self.settings.build_config()
        if not config.providers:
            QMessageBox.warning(
                self, _("Zu anderer Serie zuordnen …"), _("Kein API-Key hinterlegt."))
            return
        picker = SeriesPickerDialog(config, self.loader, episodes[0].title, self)
        if not picker.exec():
            return
        candidate = picker.selected_candidate()
        if candidate is None:
            return
        provider = next(p for p in config.providers if p.name == candidate.source)
        info = provider.details(candidate)

        updated = 0
        for item in episodes:
            episode_title, episode_overview = "", ""
            if item.season is not None and item.episode is not None:
                try:
                    ep_info = provider.episode(
                        candidate.external_id, item.season, item.episode)
                    if ep_info:
                        episode_title = ep_info.title
                        episode_overview = ep_info.overview
                except Exception:  # noqa: BLE001
                    pass
            self.library.set_match(
                Path(item.path), info, candidate.score, STATUS_MATCHED,
                season=item.season, episode=item.episode,
                episode_title=episode_title, episode_overview=episode_overview,
                note=_("Serie von Hand geaendert"))
            updated += 1

        self.refresh_view()
        QMessageBox.information(
            self, _("Zu anderer Serie zuordnen …"),
            _('{n} Episode(n) der Serie "{title}" zugeordnet.').format(
                n=updated, title=info.title))

    # --- Umbenennen -----------------------------------------------------
    def rename_preview(self) -> None:
        # Mit Auswahl nur diese umbenennen - sonst wie bisher die ganze
        # Bibliothek, konsistent zu auto_match().
        items = self._selected_movies() + self._selected_episodes()
        if not items:
            items = self.library.all_items()
        ops = renamer.build_plan(
            items, self.settings.movie_template, self.settings.series_template)
        unchanged = sum(1 for op in ops if op.status == "same")
        pending = [op for op in ops if op.status != "same"]
        if not pending:
            QMessageBox.information(
                self, _("Umbenennen …"),
                _("Nichts zu tun - alle Dateien bereits korrekt benannt."))
            return
        dialog = RenameDialog(pending, self.library, unchanged, self)
        if dialog.exec():
            self.refresh_view()

    # --- NFO fuer Kodi/Jellyfin -----------------------------------------
    def write_nfo_files(self) -> None:
        # Mit Auswahl nur diese - sonst alle zugeordneten Filme/Episoden.
        items = self._selected_movies() + self._selected_episodes()
        if not items:
            items = self.library.all_items()
        items = [i for i in items if i.status == STATUS_MATCHED]
        if not items:
            QMessageBox.information(
                self, _("NFO erzeugen (Kodi/Jellyfin)"),
                _("Keine zugeordneten Dateien ausgewaehlt."))
            return

        provider = self._tmdb_provider()
        written = 0
        errors: list[str] = []
        tvshow_done: set[Path] = set()
        progress = QProgressDialog(
            _("Erzeuge NFO-Dateien …"), _("Abbrechen"), 0, len(items), self)
        progress.setWindowModality(Qt.WindowModal)
        for i, item in enumerate(items, 1):
            if progress.wasCanceled():
                break
            progress.setValue(i - 1)
            progress.setLabelText(Path(item.path).name)
            QApplication.processEvents()
            try:
                nfo.write_for_item(item, tvshow_done, provider,
                                   save_posters=self.settings.save_local_posters)
                written += 1
            except OSError as exc:
                errors.append(f"{Path(item.path).name}: {exc}")
        progress.setValue(len(items))

        message = _("{n} NFO-Datei(en) erzeugt.").format(n=written)
        if errors:
            QMessageBox.warning(
                self, _("NFO erzeugen (Kodi/Jellyfin)"),
                message + "\n" + "\n".join(errors))
        else:
            QMessageBox.information(
                self, _("NFO erzeugen (Kodi/Jellyfin)"), message)

    # --- Untertitel -------------------------------------------------------
    def download_subtitles(self) -> None:
        client = self.settings.build_subtitle_client()
        if client is None:
            QMessageBox.warning(
                self, _("Untertitel herunterladen …"),
                _("OpenSubtitles ist nicht eingerichtet - API-Key in den "
                  "Einstellungen unter \"Untertitel\" hinterlegen."))
            return

        languages = self.settings.subtitle_language_list()
        items = self._selected_movies() + self._selected_episodes()
        if not items:
            items = self.library.all_items()
        items = [i for i in items if i.status == STATUS_MATCHED]

        jobs: list[tuple[Item, list[str]]] = []
        for item in items:
            missing = subtitles.missing_languages(Path(item.path), languages)
            if missing:
                jobs.append((item, missing))
        if not jobs:
            QMessageBox.information(
                self, _("Untertitel herunterladen …"),
                _("Nichts zu tun - alle Untertitel bereits vorhanden."))
            return

        total = sum(len(langs) for _, langs in jobs)
        progress = QProgressDialog(
            _("Suche Untertitel …"), _("Abbrechen"), 0, total, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setAutoClose(False)
        progress.setAutoReset(False)

        counts = {subtitles.STATUS_OK: 0, subtitles.STATUS_NONE: 0,
                 subtitles.STATUS_ERROR: 0}
        errors: list[str] = []

        def on_result(result) -> None:
            counts[result.status] = counts.get(result.status, 0) + 1
            # Auch bei "kein Treffer" den Grund zeigen, falls die Suche selbst
            # fehlschlug (z. B. ungueltiger API-Key) - sonst wirkt das wie
            # ein Treffer-Problem statt eines Einrichtungsfehlers.
            if result.detail and result.status in (
                    subtitles.STATUS_ERROR, subtitles.STATUS_NONE):
                errors.append(f"{result.path.name} ({result.language}): {result.detail}")

        thread, worker = subtitles.run_in_thread(jobs, client)
        worker.progress.connect(lambda i, n, name: (
            progress.setMaximum(n), progress.setValue(i), progress.setLabelText(name)))
        worker.result.connect(on_result)
        progress.canceled.connect(worker.stop)
        thread.finished.connect(progress.close)
        self._subtitle_thread, self._subtitle_worker = thread, worker
        thread.start()
        progress.exec()
        thread.wait(5000)

        message = _(
            "{ok} heruntergeladen, {none} ohne Treffer, {err} Fehler."
        ).format(ok=counts[subtitles.STATUS_OK], none=counts[subtitles.STATUS_NONE],
                err=counts[subtitles.STATUS_ERROR])
        if errors:
            QMessageBox.warning(
                self, _("Untertitel herunterladen …"),
                message + "\n" + "\n".join(errors[:10]))
        else:
            QMessageBox.information(self, _("Untertitel herunterladen …"), message)

    # --- Sichern --------------------------------------------------------
    def backup_library(self) -> None:
        """Kopiert die Bibliotheksdatenbank an einen selbst gewaehlten Ort -
        sie ist die einzige Quelle der Wahrheit fuer Zuordnungen, dafuer gibt
        es sonst keine Sicherung. Ueberschreiben laesst sie sich einfach
        durch Zurueckkopieren bei geschlossener App."""
        suggested = f"moviedesk-backup-{datetime.now():%Y-%m-%d}.sqlite"
        path, _filter = QFileDialog.getSaveFileName(
            self, _("Bibliothek sichern …"), suggested, "SQLite (*.sqlite)")
        if not path:
            return
        try:
            self.library.backup_to(Path(path))
        except OSError as exc:
            QMessageBox.warning(
                self, _("Bibliothek sichern …"),
                _("Sicherung fehlgeschlagen: {error}").format(error=exc))
            return
        self.statusBar().showMessage(
            _("Bibliothek gesichert nach {path}").format(path=path), 5000)

    # --- Einstellungen -----------------------------------------------
    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() and dialog.result_settings:
            self.settings = dialog.result_settings
            self.settings.save(self.qsettings)
            set_language(self.settings.language)

    def open_help(self) -> None:
        HelpDialog(self).exec()

    # --- Ansicht aktualisieren -----------------------------------------
    def refresh_view(self) -> None:
        self._fill_collections()
        self._fill_movies()
        self._fill_series()

    def _on_search_changed(self, text: str) -> None:
        # Nur die Listen neu aufbauen - nicht refresh_view(), das wuerde bei
        # ausgewaehlter Sammlung/Serie auch den TMDb-Abgleich fuer "fehlende
        # Filme/Episoden" bei jedem Tastendruck erneut anstossen.
        self._search_text = text.strip().lower()
        self._fill_movies()
        self._fill_series()

    def _fill_collections(self) -> None:
        current = self.collection_list.currentItem()
        current_name = current.data(Qt.UserRole) if current else None
        self.collection_list.blockSignals(True)
        self.collection_list.clear()
        all_item = QListWidgetItem(_("Alle Filme"))
        all_item.setData(Qt.UserRole, None)
        self.collection_list.addItem(all_item)
        selected_row = 0
        for row, (name, count) in enumerate(self.library.collections(), start=1):
            list_item = QListWidgetItem(f"{name}  ({count})")
            list_item.setData(Qt.UserRole, name)
            self.collection_list.addItem(list_item)
            if name == current_name:
                selected_row = row
        self.collection_list.setCurrentRow(selected_row)
        self.collection_list.blockSignals(False)

    def _selected_collection(self) -> str | None:
        item = self.collection_list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _on_collection_selected(self) -> None:
        self._fill_movies()
        collection = self._selected_collection()
        self.missing_movies_button.setEnabled(bool(collection))
        if collection:
            # Automatisch anzeigen, was in der Sammlung fehlt - keine
            # Fehlermeldungen, falls TMDb/API-Key (noch) nicht passt, das
            # macht nur der Button ausdruecklich sichtbar.
            self._check_missing_movies(silent=True)

    def _fill_movies(self) -> None:
        # Auswahl ueber Neuaufbau hinweg merken - sonst muesste man nach
        # jeder Aktion (Umbenennen, Scan, ...) den Film erneut anklicken.
        # Ueber `id` statt `path`, weil Umbenennen den Pfad aendert, die
        # Datenbankzeile (und damit die id) aber dieselbe bleibt.
        selected_ids = {i.data(Qt.UserRole).id
                       for i in self.movie_list.selectedItems()}
        self.movie_list.clear()
        to_reselect = []
        for item in self.library.list_movies(self._selected_collection()):
            if self._search_text and not (
                    self._search_text in (item.title or "").lower()
                    or self._search_text in Path(item.path).name.lower()):
                continue
            list_item = QListWidgetItem(item.title or Path(item.path).stem)
            list_item.setData(Qt.UserRole, item)
            list_item.setData(SUBTITLE_ROLE, str(item.year) if item.year else "")
            list_item.setData(STATUS_ROLE, item.status)
            list_item.setToolTip(f"{item.path}\n{STATUS_LABEL.get(item.status, item.status)}")
            pm = self.loader.get(item.poster_url) if item.poster_url else None
            if pm and not pm.isNull():
                list_item.setIcon(QIcon(pm))
            self.movie_list.addItem(list_item)
            if item.id in selected_ids:
                to_reselect.append(list_item)
        if to_reselect:
            self.movie_list.setCurrentItem(to_reselect[0])
            for list_item in to_reselect:
                list_item.setSelected(True)

    def _series_matches(self, title: str, episodes: list[Item]) -> bool:
        """Serie passt zur Suche - ueber Serientitel, Episodentitel (z. B.
        "White Christmas" findet "Black Mirror") oder Dateinamen. Letzteres
        hilft, eine Datei wiederzufinden, die versehentlich der falschen
        Serie zugeordnet wurde."""
        if self._search_text in title.lower():
            return True
        return any(
            self._search_text in (e.episode_title or "").lower()
            or self._search_text in Path(e.path).name.lower()
            for e in episodes)

    def _fill_series(self) -> None:
        # Auswahl ueber Neuaufbau hinweg merken - sonst muesste man nach
        # jeder Aktion (Umbenennen, Scan, ...) die Serie erneut anklicken.
        selected_titles = {i.data(Qt.UserRole) for i in self.series_list.selectedItems()}
        self.series_list.clear()
        self._series_items = {}
        to_reselect = []
        for title, episodes in self.library.series_groups():
            if self._search_text and not self._series_matches(title, episodes):
                continue
            self._series_items[title] = episodes
            statuses = {e.status for e in episodes}
            status = STATUS_MATCHED if statuses == {STATUS_MATCHED} else "unsure"
            list_item = QListWidgetItem(title)
            list_item.setData(Qt.UserRole, title)
            list_item.setData(
                SUBTITLE_ROLE,
                _("{n} Episode(n)").format(n=len(episodes)))
            list_item.setData(STATUS_ROLE, status)
            list_item.setToolTip(f"{title}\n{STATUS_LABEL.get(status, status)}")
            poster_url = next((e.poster_url for e in episodes if e.poster_url), None)
            pm = self.loader.get(poster_url) if poster_url else None
            if pm and not pm.isNull():
                list_item.setIcon(QIcon(pm))
            self.series_list.addItem(list_item)
            if title in selected_titles:
                to_reselect.append(list_item)
        if to_reselect:
            self.series_list.setCurrentItem(to_reselect[0])
            for list_item in to_reselect:
                list_item.setSelected(True)

    # --- Fehlende Filme/Episoden ----------------------------------------
    def _tmdb_provider(self):
        for provider in self.settings.build_providers():
            if provider.name == "tmdb":
                return provider
        return None

    def _refresh_missing_movies(self) -> None:
        """Manueller Neuabgleich - im Gegensatz zur automatischen Anzeige
        beim Auswaehlen meldet dieser Weg auch, wenn etwas nicht klappt."""
        self._fill_movies()
        self._check_missing_movies(silent=False)

    def _check_missing_movies(self, silent: bool = False) -> None:
        collection = self._selected_collection()
        if not collection:
            return
        owned = self.library.list_movies(collection)
        collection_id = next(
            (m.collection_id for m in owned if m.source == "tmdb" and m.collection_id),
            "")
        if not collection_id:
            if not silent:
                QMessageBox.information(
                    self, _("Fehlende Filme"),
                    _("Nur fuer TMDb-Sammlungen verfuegbar - eigene Sammlungen "
                      "haben keine vollstaendige Liste als Vergleich."))
            return
        provider = self._tmdb_provider()
        if provider is None:
            if not silent:
                QMessageBox.warning(
                    self, _("Fehlende Filme"), _("Kein API-Key hinterlegt."))
            return
        try:
            all_movies = provider.collection_movies(collection_id)
        except Exception as exc:  # noqa: BLE001
            if not silent:
                QMessageBox.warning(self, _("Fehlende Filme"), str(exc))
            return

        owned_ids = {m.external_id for m in owned if m.source == "tmdb"}
        missing = [m for m in all_movies if m.tmdb_id not in owned_ids]
        for movie in missing:
            item = Item(id=MISSING_ID, kind=LIB_MOVIE, path="", root="",
                       title=movie.title, year=movie.year,
                       poster_url=movie.poster_url, status="missing")
            list_item = QListWidgetItem(item.title)
            list_item.setData(Qt.UserRole, item)
            list_item.setData(SUBTITLE_ROLE, str(item.year) if item.year else "")
            list_item.setData(STATUS_ROLE, "missing")
            list_item.setToolTip(_("Fehlt in deiner Sammlung"))
            pm = self.loader.get(item.poster_url) if item.poster_url else None
            if pm and not pm.isNull():
                list_item.setIcon(QIcon(pm))
            self.movie_list.addItem(list_item)
        if not missing and not silent:
            QMessageBox.information(
                self, _("Fehlende Filme"),
                _("Vollstaendig - alle Filme dieser Reihe sind vorhanden."))

    def _refresh_missing_episodes(self) -> None:
        items = self.series_list.selectedItems()
        if not items:
            return
        self._fill_episode_table(items[0].data(Qt.UserRole))
        self._check_missing_episodes(silent=False)

    def _check_missing_episodes(self, silent: bool = False) -> None:
        items = self.series_list.selectedItems()
        if not items:
            return
        title = items[0].data(Qt.UserRole)
        owned = self._series_items.get(title, [])
        series_id = next(
            (e.external_id for e in owned if e.source == "tmdb" and e.external_id), "")
        if not series_id:
            if not silent:
                QMessageBox.information(
                    self, _("Fehlende Episoden"),
                    _("Diese Serie ist nicht ueber TMDb zugeordnet."))
            return
        provider = self._tmdb_provider()
        if provider is None:
            if not silent:
                QMessageBox.warning(
                    self, _("Fehlende Episoden"), _("Kein API-Key hinterlegt."))
            return
        try:
            roster = provider.series_roster(series_id)
        except Exception as exc:  # noqa: BLE001
            if not silent:
                QMessageBox.warning(self, _("Fehlende Episoden"), str(exc))
            return

        owned_pairs = {(e.season, e.episode) for e in owned}
        missing = [e for e in roster if (e.season, e.episode) not in owned_pairs]
        self.episode_table.setSortingEnabled(False)
        row = self.episode_table.rowCount()
        self.episode_table.setRowCount(row + len(missing))
        for ep in missing:
            item = Item(id=MISSING_ID, kind=EPISODE, path="", root="",
                       title=title, season=ep.season, episode=ep.episode,
                       episode_title=ep.title, status="missing")
            tag_item = QTableWidgetItem(f"S{ep.season:02d}E{ep.episode:02d}")
            tag_item.setData(Qt.UserRole, item)
            self.episode_table.setItem(row, 0, tag_item)
            self.episode_table.setItem(row, 1, QTableWidgetItem(ep.title))
            self.episode_table.setItem(row, 2, QTableWidgetItem(""))
            self.episode_table.setItem(
                row, 3, QTableWidgetItem(STATUS_LABEL["missing"]))
            row += 1
        self.episode_table.setSortingEnabled(True)
        if not missing and not silent:
            QMessageBox.information(
                self, _("Fehlende Episoden"),
                _("Vollstaendig - alle Episoden sind vorhanden."))

    # --- Fehlende Teile (alle Sammlungen/Serien) -------------------------
    def show_missing_overview(self) -> None:
        provider = self._tmdb_provider()
        if provider is None:
            QMessageBox.warning(
                self, _("Fehlende Teile"), _("Kein API-Key hinterlegt."))
            return

        dialog = missingdialog.MissingOverviewDialog(
            self.settings.only_released_missing, self.settings.release_country, self)
        thread, worker = missingdialog.run_in_thread(
            self.library, provider, self.settings.only_released_missing,
            self.settings.release_country)
        worker.progress.connect(dialog.set_progress)
        worker.finished.connect(dialog.show_results)
        self._missing_thread, self._missing_worker = thread, worker
        thread.start()
        dialog.exec()
        thread.wait(5000)

        if dialog.jump_to_collection:
            self._jump_to_collection(dialog.jump_to_collection)
        elif dialog.jump_to_series:
            self._jump_to_series(dialog.jump_to_series)

    def _jump_to_collection(self, name: str) -> None:
        self.tabs.setCurrentIndex(0)
        for row in range(self.collection_list.count()):
            if self.collection_list.item(row).data(Qt.UserRole) == name:
                self.collection_list.setCurrentRow(row)
                break

    def _jump_to_series(self, title: str) -> None:
        self.tabs.setCurrentIndex(1)
        for row in range(self.series_list.count()):
            if self.series_list.item(row).data(Qt.UserRole) == title:
                self.series_list.setCurrentRow(row)
                break

    # --- Auswahl -----------------------------------------------------
    def _current_movie(self) -> Item | None:
        items = self.movie_list.selectedItems()
        if not items:
            return None
        item: Item = items[0].data(Qt.UserRole)
        return item if item.id != MISSING_ID else None

    def _selected_movies(self) -> list[Item]:
        if self.tabs.currentIndex() != 0:
            return []
        return [i.data(Qt.UserRole) for i in self.movie_list.selectedItems()
               if i.data(Qt.UserRole).id != MISSING_ID]

    def _selected_episodes(self) -> list[Item]:
        if self.tabs.currentIndex() != 1:
            return []
        rows = {i.row() for i in self.episode_table.selectedItems()}
        items = [self.episode_table.item(row, 0).data(Qt.UserRole) for row in rows]
        return [i for i in items if i.id != MISSING_ID]

    # --- Kontextmenues ----------------------------------------------------
    def _movie_context_menu(self, pos) -> None:
        movies = self._selected_movies()
        if not movies:
            return
        menu = QMenu(self)
        if len(movies) == 1:
            menu.addAction(tool_icon("play"), _("Abspielen"),
                           lambda: self._play(movies[0]))
            menu.addSeparator()
        menu.addAction(self.actions_map["auto_match"])
        if len(movies) == 1:
            menu.addAction(_("Manuell zuordnen …"),
                           lambda: self._manual_match(movies[0]))
            menu.addAction(
                tool_icon("refresh"), _("Nur diesen Film scannen"),
                # Erst starten, wenn das Kontextmenue sich geschlossen hat -
                # ein QThread + modaler Dialog waehrend dessen eigener
                # Event-Schleife (Popup-Grab) kann sonst abstuerzen.
                lambda: QTimer.singleShot(0, lambda: self._scan_movie(movies[0])))
        menu.addSeparator()
        menu.addAction(_("Zu Sammlung hinzufuegen …"),
                       lambda: self._add_to_collection(movies))
        if any(m.custom_collection for m in movies):
            menu.addAction(_("Aus eigener Sammlung entfernen"),
                           lambda: self._remove_from_collection(movies))
        menu.addSeparator()
        menu.addAction(self.actions_map["rename"])
        menu.addAction(self.actions_map["nfo"])
        menu.addAction(self.actions_map["subtitles"])
        menu.addSeparator()
        menu.addAction(self.actions_map["delete"])
        menu.exec(self.movie_list.viewport().mapToGlobal(pos))

    def _episode_context_menu(self, pos) -> None:
        episodes = self._selected_episodes()
        if not episodes:
            return
        menu = QMenu(self)
        if len(episodes) == 1:
            menu.addAction(tool_icon("play"), _("Abspielen"),
                           lambda: self._play(episodes[0]))
            menu.addSeparator()
        menu.addAction(self.actions_map["auto_match"])
        if len(episodes) == 1:
            menu.addAction(_("Manuell zuordnen …"),
                           lambda: self._manual_match(episodes[0]))
        menu.addAction(_("Zu anderer Staffel zuordnen …"),
                       lambda: self._reassign_season(episodes))
        menu.addAction(_("Zu anderer Serie zuordnen …"),
                       lambda: self._reassign_series(episodes))
        menu.addSeparator()
        menu.addAction(self.actions_map["rename"])
        menu.addAction(self.actions_map["nfo"])
        menu.addAction(self.actions_map["subtitles"])
        menu.addSeparator()
        menu.addAction(self.actions_map["delete"])
        menu.exec(self.episode_table.viewport().mapToGlobal(pos))

    def _select_all_episodes_of(self, title: str) -> None:
        """Serie auswaehlen und alle eigenen (nicht fehlenden) Episoden
        markieren - Grundlage fuer Sammelaktionen aus dem Serien-Kontextmenue."""
        for row in range(self.series_list.count()):
            if self.series_list.item(row).data(Qt.UserRole) == title:
                self.series_list.setCurrentRow(row)
                break
        self.episode_table.selectAll()

    def _series_action(self, title: str, action) -> None:
        self._select_all_episodes_of(title)
        action()

    def _series_context_menu(self, pos) -> None:
        items = self.series_list.selectedItems()
        if not items:
            return
        title = items[0].data(Qt.UserRole)
        menu = QMenu(self)
        menu.addAction(tool_icon("match"), _("Automatisch zuordnen"),
                       lambda: self._series_action(title, self.auto_match))
        menu.addAction(
            tool_icon("refresh"), _("Nur diese Serie scannen"),
            # Erst starten, wenn das Kontextmenue sich geschlossen hat - ein
            # QThread + modaler Dialog waehrend dessen eigener Event-Schleife
            # (Popup-Grab) kann sonst abstuerzen.
            lambda: QTimer.singleShot(0, lambda: self._scan_series(title)))
        menu.addAction(_("Fehlende Episoden aktualisieren"),
                       self._refresh_missing_episodes)
        menu.addSeparator()
        menu.addAction(tool_icon("rename"), _("Umbenennen …"),
                       lambda: self._series_action(title, self.rename_preview))
        menu.addAction(tool_icon("nfo"), _("NFO erzeugen (Kodi/Jellyfin)"),
                       lambda: self._series_action(title, self.write_nfo_files))
        menu.addAction(tool_icon("subtitle"), _("Untertitel herunterladen …"),
                       lambda: self._series_action(title, self.download_subtitles))
        menu.addSeparator()
        menu.addAction(tool_icon("delete"), _("Loeschen …"),
                       lambda: self._series_action(title, self.delete_selected))
        menu.exec(self.series_list.viewport().mapToGlobal(pos))

    def _add_to_collection(self, movies: list[Item]) -> None:
        existing = self.library.custom_collection_names()
        name, ok = QInputDialog.getItem(
            self, _("Zu Sammlung hinzufuegen …"),
            _("Name der Sammlung (neu oder vorhanden):"), existing,
            editable=True)
        name = name.strip()
        if not ok or not name:
            return
        for movie in movies:
            self.library.set_custom_collection(Path(movie.path), name)
        self.refresh_view()

    def _remove_from_collection(self, movies: list[Item]) -> None:
        for movie in movies:
            self.library.set_custom_collection(Path(movie.path), "")
        self.refresh_view()

    # --- Loeschen --------------------------------------------------------
    def delete_selected(self) -> None:
        items = self._selected_movies() or self._selected_episodes()
        if not items:
            QMessageBox.information(
                self, _("Loeschen …"), _("Bitte mindestens eine Datei waehlen."))
            return
        self._delete_items(items)

    def _known_roots(self) -> set[Path]:
        return {Path(r) for r in self.settings.movie_roots + self.settings.series_roots}

    def _delete_items(self, items: list[Item]) -> None:
        if not items:
            return
        roots = self._known_roots()
        folder_eligible = all(
            Path(i.path).parent not in roots for i in items)

        names = "\n".join(f"- {Path(i.path).name}" for i in items[:10])
        if len(items) > 10:
            names += f"\n… (+{len(items) - 10})"

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(_("Loeschen …"))
        box.setText(
            _("{n} Datei(en) in den Papierkorb verschieben?").format(n=len(items)))
        box.setInformativeText(names)
        checkbox = QCheckBox(_(
            "Ganzes Verzeichnis loeschen (inkl. aller anderen Dateien darin)"))
        checkbox.setEnabled(folder_eligible)
        if not folder_eligible:
            checkbox.setText(checkbox.text() + " " + _(
                "- nicht verfuegbar, mindestens eine Datei liegt direkt im "
                "Bibliotheksordner"))
        box.setCheckBox(checkbox)
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
        box.setDefaultButton(QMessageBox.Cancel)
        if box.exec() != QMessageBox.Yes:
            return
        whole_folder = checkbox.isChecked() and folder_eligible

        errors: list[str] = []
        done_folders: set[Path] = set()
        for item in items:
            path = Path(item.path)
            folder = path.parent
            try:
                if whole_folder:
                    if folder in done_folders:
                        continue
                    send2trash(str(folder))
                    self.library.remove_under(folder)
                    done_folders.add(folder)
                else:
                    send2trash(str(path))
                    self.library.remove_path(path)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{path.name}: {exc}")

        self.refresh_view()
        if errors:
            QMessageBox.warning(
                self, _("Loeschen …"),
                _("Nicht alles konnte geloescht werden:") + "\n" + "\n".join(errors))

    def _on_movie_selected(self) -> None:
        self.movie_meta.show_item(self._current_movie())

    def _fill_episode_table(self, title: str) -> list[Item]:
        episodes = sorted(
            self._series_items.get(title, []),
            key=lambda e: (e.season or 0, e.episode or 0))
        self.episode_table.setSortingEnabled(False)
        self.episode_table.setRowCount(len(episodes))
        for row, episode in enumerate(episodes):
            tag = f"S{episode.season:02d}E{episode.episode:02d}" \
                if episode.season is not None and episode.episode is not None else "?"
            tag_item = QTableWidgetItem(tag)
            tag_item.setData(Qt.UserRole, episode)
            self.episode_table.setItem(row, 0, tag_item)
            self.episode_table.setItem(
                row, 1, QTableWidgetItem(episode.episode_title))
            file_item = QTableWidgetItem(
                Path(episode.path).name if episode.path else "")
            file_item.setToolTip(episode.path)
            self.episode_table.setItem(row, 2, file_item)
            self.episode_table.setItem(
                row, 3, QTableWidgetItem(STATUS_LABEL.get(episode.status, episode.status)))
        self.episode_table.setSortingEnabled(True)
        self.episode_table.resizeColumnsToContents()
        return episodes

    def _on_series_selected(self) -> None:
        items = self.series_list.selectedItems()
        self.episode_table.setRowCount(0)
        self.missing_episodes_button.setEnabled(bool(items))
        if not items:
            self.series_meta.show_item(None)
            return
        title = items[0].data(Qt.UserRole)
        episodes = self._fill_episode_table(title)
        if episodes:
            self.series_meta.show_item(episodes[0])
        # Automatisch anzeigen, was laut TMDb fehlt - still, falls (noch)
        # kein API-Key oder die Serie nicht ueber TMDb zugeordnet ist.
        self._check_missing_episodes(silent=True)

    def _current_episode(self) -> Item | None:
        rows = self.episode_table.selectedItems()
        if not rows:
            return None
        item: Item = self.episode_table.item(rows[0].row(), 0).data(Qt.UserRole)
        return item if item.id != MISSING_ID else None

    def _on_episode_selected(self) -> None:
        self.series_meta.show_item(self._current_episode())

    # --- Poster --------------------------------------------------------
    def _on_poster(self, url: str, pixmap) -> None:
        if pixmap.isNull():
            return
        for widget in (self.movie_list, self.series_list):
            for row in range(widget.count()):
                list_item = widget.item(row)
                data = list_item.data(Qt.UserRole)
                item_url = data.poster_url if isinstance(data, Item) else None
                if item_url is None and isinstance(data, str):
                    episodes = self._series_items.get(data, [])
                    item_url = next(
                        (e.poster_url for e in episodes if e.poster_url), None)
                if item_url == url:
                    list_item.setIcon(QIcon(pixmap))

    def closeEvent(self, event) -> None:  # noqa: N802
        # Laufende Hintergrund-Threads (Scan/Zuordnung/Untertitel) sauber
        # beenden, statt sie beim Schliessen einfach abzuschneiden - sonst
        # drohen Warnungen/Abstuerze, weil Qt-Objekte aus dem falschen
        # Thread heraus zerstoert werden.
        for attr in ("_scan_thread", "_match_thread", "_subtitle_thread",
                    "_missing_thread"):
            thread = getattr(self, attr, None)
            worker = getattr(self, attr.replace("thread", "worker"), None)
            if thread is None or not thread.isRunning():
                continue
            if worker is not None and hasattr(worker, "stop"):
                worker.stop()
            thread.quit()
            thread.wait(5000)
        self.library.close()
        super().closeEvent(event)
