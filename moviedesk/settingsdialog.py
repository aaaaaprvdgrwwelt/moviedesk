"""API-Keys, Schwellwert, Umbenennen-Vorlagen und Bibliotheksordner."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QSlider, QTabWidget, QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt

from deskkit.widgets import RootList

from .config import Settings
from .i18n import LANGUAGES, _


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Einstellungen …"))
        self.resize(560, 480)
        self.result_settings: Settings | None = None

        tabs = QTabWidget()
        tabs.addTab(self._sources_tab(settings), _("Quellen"))
        tabs.addTab(self._subtitles_tab(settings), _("Untertitel"))
        tabs.addTab(self._rename_tab(settings), _("Umbenennen"))
        tabs.addTab(self._library_tab(settings), _("Bibliothek"))
        tabs.addTab(self._general_tab(settings), _("Allgemein"))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    def _sources_tab(self, settings: Settings) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        tmdb_box = QGroupBox("TMDb")
        self.use_tmdb = QCheckBox(_("Aktiv"))
        self.use_tmdb.setChecked(settings.use_tmdb)
        self.tmdb_key = QLineEdit(settings.tmdb_key)
        form = QFormLayout(tmdb_box)
        form.addRow(self.use_tmdb)
        form.addRow(_("API-Key"), self.tmdb_key)

        tvdb_box = QGroupBox("TheTVDB")
        self.use_tvdb = QCheckBox(_("Aktiv (Serien)"))
        self.use_tvdb.setChecked(settings.use_tvdb)
        self.tvdb_key = QLineEdit(settings.tvdb_key)
        self.tvdb_pin = QLineEdit(settings.tvdb_pin)
        form = QFormLayout(tvdb_box)
        form.addRow(self.use_tvdb)
        form.addRow(_("API-Key"), self.tvdb_key)
        form.addRow("PIN", self.tvdb_pin)

        omdb_box = QGroupBox("OMDb")
        self.use_omdb = QCheckBox(_("Aktiv (nur IMDb-Rating ergaenzen)"))
        self.use_omdb.setChecked(settings.use_omdb)
        self.omdb_key = QLineEdit(settings.omdb_key)
        form = QFormLayout(omdb_box)
        form.addRow(self.use_omdb)
        form.addRow(_("API-Key"), self.omdb_key)

        threshold_box = QGroupBox(_("Schwellwert fuer automatische Zuordnung"))
        self.threshold = QSlider(Qt.Horizontal)
        self.threshold.setRange(0, 100)
        self.threshold.setValue(settings.threshold)
        self.threshold_label = QLabel(str(settings.threshold))
        self.threshold.valueChanged.connect(
            lambda v: self.threshold_label.setText(str(v)))
        row = QHBoxLayout(threshold_box)
        row.addWidget(self.threshold, 1)
        row.addWidget(self.threshold_label)

        missing_box = QGroupBox(_("Fehlende Teile"))
        self.only_released_missing = QCheckBox(
            _("Nur bereits veroeffentlichte/ausgestrahlte fehlende Teile anzeigen"))
        self.only_released_missing.setChecked(settings.only_released_missing)
        self.release_country = QLineEdit(settings.release_country)
        self.release_country.setPlaceholderText("DE")
        self.release_country.setMaxLength(2)
        note = QLabel(_(
            "Laendercode gilt nur fuer Filme (TMDb kennt laenderspezifische "
            "Kinostarts); bei Episoden gibt es bei TMDb nur ein einziges "
            "weltweites Ausstrahlungsdatum."))
        note.setWordWrap(True)
        form = QFormLayout(missing_box)
        form.addRow(self.only_released_missing)
        form.addRow(_("Laendercode (Filme)"), self.release_country)
        form.addRow(note)

        layout.addWidget(tmdb_box)
        layout.addWidget(tvdb_box)
        layout.addWidget(omdb_box)
        layout.addWidget(threshold_box)
        layout.addWidget(missing_box)
        layout.addStretch(1)
        return widget

    def _subtitles_tab(self, settings: Settings) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        box = QGroupBox("OpenSubtitles.com")
        self.use_subtitles = QCheckBox(_("Aktiv"))
        self.use_subtitles.setChecked(settings.use_subtitles)
        self.opensubtitles_key = QLineEdit(settings.opensubtitles_key)
        self.opensubtitles_user = QLineEdit(settings.opensubtitles_user)
        self.opensubtitles_pass = QLineEdit(settings.opensubtitles_pass)
        self.opensubtitles_pass.setEchoMode(QLineEdit.Password)
        self.subtitle_languages = QLineEdit(settings.subtitle_languages)
        self.subtitle_languages.setPlaceholderText("de,en")

        form = QFormLayout(box)
        form.addRow(self.use_subtitles)
        form.addRow(_("API-Key"), self.opensubtitles_key)
        form.addRow(_("Benutzername"), self.opensubtitles_user)
        form.addRow(_("Passwort"), self.opensubtitles_pass)
        form.addRow(_("Sprachen (Komma-getrennt)"), self.subtitle_languages)

        note = QLabel(_(
            "Benutzername/Passwort sind fuer einen normalen OpenSubtitles.com-"
            "Account - ohne Login gilt nur ein sehr kleines Tages-Limit fuer "
            "Downloads. Das Passwort wird wie der API-Key unverschluesselt "
            "lokal gespeichert."))
        note.setWordWrap(True)

        layout.addWidget(box)
        layout.addWidget(note)
        layout.addStretch(1)
        return widget

    def _rename_tab(self, settings: Settings) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        layout.addWidget(QLabel(
            _("Platzhalter Filme: {title} {year} {ext}")))
        self.movie_template = QLineEdit(settings.movie_template)
        layout.addWidget(self.movie_template)

        layout.addWidget(QLabel(
            _("Platzhalter Serien: {series} {year} {season} {episode} "
              "{episode_title} {ext} - {year} ist das Jahr der Erstausstrahlung")))
        self.series_template = QLineEdit(settings.series_template)
        layout.addWidget(self.series_template)
        layout.addStretch(1)
        return widget

    def _library_tab(self, settings: Settings) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel(_("Filme-Ordner")))
        self.movie_roots = RootList(settings.movie_roots, _)
        layout.addWidget(self.movie_roots)
        layout.addWidget(QLabel(_("Serien-Ordner")))
        self.series_roots = RootList(settings.series_roots, _)
        layout.addWidget(self.series_roots)

        self.save_local_posters = QCheckBox(
            _('"poster.jpg" zusaetzlich lokal neben Film/Serie speichern '
              "(bei \"NFO erzeugen\") - lesen Kodi/Jellyfin/Plex auch ohne "
              "Internetzugriff"))
        self.save_local_posters.setChecked(settings.save_local_posters)
        layout.addWidget(self.save_local_posters)
        return widget

    def _general_tab(self, settings: Settings) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)
        self.language = QComboBox()
        for code, label in LANGUAGES.items():
            self.language.addItem(label, code)
        index = self.language.findData(settings.language)
        if index >= 0:
            self.language.setCurrentIndex(index)
        form.addRow(_("Sprache"), self.language)
        return widget

    # ------------------------------------------------------------------
    def _accept(self) -> None:
        self.result_settings = Settings(
            tmdb_key=self.tmdb_key.text().strip(),
            use_tmdb=self.use_tmdb.isChecked(),
            omdb_key=self.omdb_key.text().strip(),
            use_omdb=self.use_omdb.isChecked(),
            tvdb_key=self.tvdb_key.text().strip(),
            tvdb_pin=self.tvdb_pin.text().strip(),
            use_tvdb=self.use_tvdb.isChecked(),
            threshold=self.threshold.value(),
            movie_template=self.movie_template.text().strip(),
            series_template=self.series_template.text().strip(),
            movie_roots=self.movie_roots.roots(),
            series_roots=self.series_roots.roots(),
            language=self.language.currentData(),
            opensubtitles_key=self.opensubtitles_key.text().strip(),
            opensubtitles_user=self.opensubtitles_user.text().strip(),
            opensubtitles_pass=self.opensubtitles_pass.text(),
            use_subtitles=self.use_subtitles.isChecked(),
            subtitle_languages=self.subtitle_languages.text().strip() or "de,en",
            save_local_posters=self.save_local_posters.isChecked(),
            only_released_missing=self.only_released_missing.isChecked(),
            release_country=(self.release_country.text().strip() or "DE").upper(),
        )
        self.accept()
