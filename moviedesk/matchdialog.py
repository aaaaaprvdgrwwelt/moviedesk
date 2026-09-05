"""Treffer von Hand auswaehlen, wenn die Automatik unsicher war oder nichts fand."""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, QThread, Signal
from PySide6.QtGui import QIntValidator, QPixmap
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSpinBox,
    QTextBrowser, QVBoxLayout, QWidget,
)

from .i18n import _
from .library import EPISODE, Item, LibraryIndex, STATUS_MATCHED
from .matcher import MatchConfig, apply_supplements, collect_candidates
from .parser import parse_episode
from .providers.base import MOVIE, SERIES, Candidate, SearchQuery
from .thumbs import PosterLoader

POSTER_W, ROW_H = 60, 88

#: Erkennt sowohl "https://www.themoviedb.org/movie/1548113-..." als auch
#: ".../tv/12345-..." - daraus lassen sich ID *und* Art (Film/Serie) lesen.
_TMDB_URL_RE = re.compile(r"themoviedb\.org/(movie|tv)/(\d+)")
#: IMDb-IDs sehen ueberall gleich aus ("tt1832489"), egal ob als blanke ID
#: oder aus einer imdb.com-URL kopiert.
_IMDB_RE = re.compile(r"tt\d{6,9}")
#: TheTVDB fuehrt die numerische ID am Ende einer Episoden-URL nur als
#: Episoden-ID, nicht als Serien-ID - die Serie muss erst darueber
#: nachgeschlagen werden (siehe `_load_direct`).
_TVDB_EPISODE_URL_RE = re.compile(r"thetvdb\.com/series/[\w-]+/episodes/(\d+)")
_DIGITS_RE = re.compile(r"\d+")


def _parse_reference(text: str) -> tuple[str, str, str | None] | None:
    """(Quelle "tmdb"/"imdb"/"tvdb_episode", ID, Art) aus einer eingefuegten
    URL/ID lesen.

    Bei einer nackten TMDb-Zahl oder einer IMDb-ID bleibt die Art unbekannt
    (None) - dann entscheidet der Aufrufer anhand der Datei."""
    match = _TMDB_URL_RE.search(text)
    if match:
        kind = MOVIE if match.group(1) == "movie" else SERIES
        return "tmdb", match.group(2), kind
    match = _IMDB_RE.search(text)
    if match:
        return "imdb", match.group(0), None
    match = _TVDB_EPISODE_URL_RE.search(text)
    if match:
        return "tvdb_episode", match.group(1), SERIES
    match = _DIGITS_RE.search(text)
    if match:
        return "tmdb", match.group(0), None
    return None


def find_provider(config: MatchConfig, name: str):
    return next((p for p in config.providers if p.name == name), None)


def _resolve_tmdb_by_imdb(config: MatchConfig, imdb_id: str, preferred_kind: str):
    """(MediaInfo, Art) ueber TMDbs IMDb-Verknuepfung, oder (None, None),
    wenn TMDb nicht eingerichtet ist oder die ID nicht kennt."""
    tmdb = find_provider(config, "tmdb")
    if tmdb is None:
        return None, None
    try:
        found = tmdb.find_by_imdb(imdb_id)
    except Exception:  # noqa: BLE001
        return None, None
    movies = found.get("movie_results") or []
    shows = found.get("tv_results") or []
    # Bevorzugt die zur Datei passende Art - faellt aber auf die jeweils
    # andere zurueck, falls TMDb es dort katalogisiert hat (genau der Fall,
    # der die IMDb-Eingabe ueberhaupt noetig macht).
    if preferred_kind == MOVIE:
        results, kind = (movies, MOVIE) if movies else (shows, SERIES)
    else:
        results, kind = (shows, SERIES) if shows else (movies, MOVIE)
    if not results:
        return None, None
    candidate = Candidate(source="tmdb", external_id=str(results[0]["id"]),
                          kind=kind, title="")
    return tmdb.details(candidate), kind


def resolve_reference(config: MatchConfig, text: str, preferred_kind: str):
    """Loest eine eingefuegte TMDb-/IMDb-/TheTVDB-Episoden-Referenz zu
    vollen Metadaten auf. Gibt (MediaInfo, Art, gefundene_Staffel,
    gefundene_Episode) zurueck - die letzten beiden sind nur bei einem
    TheTVDB-Episoden-Link belegt. Wirft ValueError mit einer fuer den
    Nutzer verstaendlichen Meldung, wenn nichts gefunden wurde."""
    parsed = _parse_reference(text)
    if parsed is None:
        raise ValueError(
            _("Konnte keine TMDb-, IMDb- oder TheTVDB-ID aus der Eingabe lesen."))
    source, ref_id, kind = parsed
    preferred_kind = kind or preferred_kind
    found_season = found_episode = None

    if source == "tvdb_episode":
        tvdb = find_provider(config, "tvdb")
        if tvdb is None or not tvdb.available()[0]:
            raise ValueError(_("TheTVDB ist nicht eingerichtet."))
        ep_data = tvdb.episode_by_id(ref_id)
        series_id = ep_data.get("seriesId")
        if series_id is None:
            raise ValueError(_("Konnte die Serie zu dieser Episode nicht ermitteln."))
        candidate = Candidate(source="tvdb", external_id=str(series_id),
                              kind=SERIES, title="")
        info = tvdb.details(candidate)
        kind = SERIES
        # TheTVDB kennt zu dieser Episode direkt Staffel/Episode - das nimmt
        # einem das Nachschlagen ab (z. B. bei einer absoluten Folgenzaehlung
        # wie "die 100. Folge").
        found_season = ep_data.get("seasonNumber")
        found_episode = ep_data.get("number")
    elif source == "imdb":
        info, kind = _resolve_tmdb_by_imdb(config, ref_id, preferred_kind)
        if info is None:
            # TMDb kennt die ID nicht (oder ist nicht eingerichtet) - OMDb
            # greift direkt auf IMDbs eigene Daten zu und findet manchen
            # Titel, den TMDb (noch) nicht verknuepft hat.
            omdb = find_provider(config, "omdb")
            if omdb is None or not omdb.available()[0]:
                raise ValueError(_("Weder TMDb noch OMDb kennen diese IMDb-ID."))
            info = omdb.find_by_imdb(ref_id)
            if info is None:
                raise ValueError(_("Weder TMDb noch OMDb kennen diese IMDb-ID."))
            kind = info.kind
    else:
        tmdb = find_provider(config, "tmdb")
        if tmdb is None:
            raise ValueError(_("TMDb ist nicht eingerichtet."))
        kind = preferred_kind
        candidate = Candidate(source="tmdb", external_id=ref_id, kind=kind, title="")
        info = tmdb.details(candidate)

    return info, kind, found_season, found_episode


class _SearchWorker(QObject):
    done = Signal(object, str)

    def __init__(self, query: SearchQuery, config: MatchConfig):
        super().__init__()
        self.query, self.config = query, config

    def run(self) -> None:
        candidates, notes = collect_candidates(self.query, self.config)
        self.done.emit(candidates, notes)


def stop_search_thread(thread: QThread | None) -> None:
    """Laufenden Such-Thread sauber beenden, bevor ein Dialog verschwindet -
    sonst droht ein Absturz, weil Qt-Objekte aus dem falschen Thread heraus
    zerstoert werden, waehrend der Thread noch arbeitet."""
    if thread is None:
        return
    try:
        if thread.isRunning():
            thread.quit()
            thread.wait(3000)
    except RuntimeError:
        # Das C++-Objekt ist schon weg (Thread war laengst fertig und wurde
        # per deleteLater() abgeraeumt) - dann gibt es nichts mehr zu tun.
        pass


class MatchDialog(QDialog):
    def __init__(self, item: Item, config: MatchConfig, library: LibraryIndex,
                loader: PosterLoader, parent=None):
        super().__init__(parent)
        self.item = item
        self.config = config
        self.library = library
        self.loader = loader
        self.loader.ready.connect(self._on_poster)
        self._candidates: list[Candidate] = []
        self._thread: QThread | None = None

        self.setWindowTitle(_("Treffer waehlen") + f" - {Path(item.path).name}")
        self.resize(640, 480)

        self.title_edit = QLineEdit(item.title)
        self.year_edit = QLineEdit(str(item.year) if item.year else "")
        self.year_edit.setPlaceholderText(_("(unbekannt)"))
        self.year_edit.setValidator(QIntValidator(1900, 2100, self.year_edit))
        self.year_edit.setMaximumWidth(90)

        form = QFormLayout()
        form.addRow(_("Titel"), self.title_edit)
        form.addRow(_("Jahr"), self.year_edit)

        if item.kind == EPISODE:
            self.season_edit = QSpinBox()
            self.season_edit.setRange(0, 99)
            self.season_edit.setValue(item.season or 0)
            self.episode_edit = QSpinBox()
            self.episode_edit.setRange(0, 999)
            self.episode_edit.setValue(item.episode or 0)
            row = QHBoxLayout()
            row.addWidget(self.season_edit)
            row.addWidget(self.episode_edit)
            wrapper = QWidget()
            wrapper.setLayout(row)
            form.addRow(_("Staffel / Episode"), wrapper)
        else:
            self.season_edit = self.episode_edit = None

        search_button = QPushButton(_("Suchen"))
        search_button.clicked.connect(self.search)
        # Enter im Titel-/Jahresfeld soll suchen, nicht versehentlich den
        # aktuell (evtl. noch von der letzten Suche her) markierten Treffer
        # bestaetigen - siehe ok_button.setAutoDefault(False) unten.
        self.title_edit.returnPressed.connect(self.search)
        self.year_edit.returnPressed.connect(self.search)

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

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        self.ok_button = buttons.button(QDialogButtonBox.Ok)
        self.ok_button.setEnabled(False)
        # Ohne das faengt der OK-Button per Qt-Vorgabe die Enter-Taste ab,
        # egal in welchem Feld man gerade tippt - lieber muss OK bewusst
        # angeklickt werden.
        self.ok_button.setAutoDefault(False)
        self.ok_button.setDefault(False)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(search_button)
        layout.addLayout(direct_row)
        layout.addWidget(self.list, 1)
        layout.addWidget(self.overview)
        layout.addWidget(buttons)

        self.search()

    # ------------------------------------------------------------------
    def _query(self) -> SearchQuery:
        kind = MOVIE if self.item.kind != EPISODE else SERIES
        text = self.year_edit.text().strip()
        year = int(text) if text else None
        if self.item.kind == EPISODE:
            return SearchQuery(kind=kind, title=self.title_edit.text().strip(),
                              year=year, season=self.season_edit.value(),
                              episode=self.episode_edit.value())
        return SearchQuery(kind=kind, title=self.title_edit.text().strip(), year=year)

    def search(self) -> None:
        self.list.clear()
        self.ok_button.setEnabled(False)
        query = self._query()
        if not query.title:
            return
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
        self._candidates = candidates
        for candidate in candidates:
            year = f" ({candidate.year})" if candidate.year else ""
            text = f"{candidate.title}{year}  ·  {candidate.score}%"
            list_item = QListWidgetItem(text)
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
        preferred_kind = SERIES if self.item.kind == EPISODE else MOVIE
        try:
            info, kind, found_season, found_episode = resolve_reference(
                self.config, text, preferred_kind)
        except ValueError as exc:
            QMessageBox.warning(self, _("TMDb-/IMDb-/TheTVDB-Link"), str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, _("TMDb-/IMDb-/TheTVDB-Link"), str(exc))
            return

        candidate = Candidate(
            source=info.source, external_id=info.external_id, kind=kind,
            title=info.title, year=info.year, overview=info.overview,
            poster_url=info.poster_url, rating=info.rating, score=100)

        if self.item.kind == EPISODE and found_season is not None \
                and found_episode is not None:
            self.season_edit.setValue(found_season)
            self.episode_edit.setValue(found_episode)

        self.list.clear()
        self._candidates = [candidate]
        year = f" ({candidate.year})" if candidate.year else ""
        art = _("Film") if kind == MOVIE else _("Serie")
        list_item = QListWidgetItem(
            f"{candidate.title}{year}  ·  {art}, manuell gewaehlt "
            f"({info.source.upper()})")
        list_item.setData(Qt.UserRole, candidate)
        pm = self.loader.get(candidate.poster_url) if candidate.poster_url else None
        if pm and not pm.isNull():
            list_item.setIcon(pm)
        self.list.addItem(list_item)
        self.list.setCurrentRow(0)

    def _on_poster(self, url: str, pixmap: QPixmap) -> None:
        for row in range(self.list.count()):
            item = self.list.item(row)
            candidate: Candidate = item.data(Qt.UserRole)
            if candidate.poster_url == url and not pixmap.isNull():
                item.setIcon(pixmap)

    def _show_overview(self) -> None:
        items = self.list.selectedItems()
        self.ok_button.setEnabled(bool(items))
        if not items:
            return
        candidate: Candidate = items[0].data(Qt.UserRole)
        self.overview.setPlainText(candidate.overview)

    def done(self, result: int) -> None:  # noqa: N802 - Qt-Namenskonvention
        stop_search_thread(self._thread)
        super().done(result)

    def _accept(self) -> None:
        items = self.list.selectedItems()
        if not items:
            return
        candidate: Candidate = items[0].data(Qt.UserRole)
        provider = next(p for p in self.config.providers if p.name == candidate.source)
        info = provider.details(candidate)
        query = self._query()
        apply_supplements(info, query, self.config.providers)
        path = Path(self.item.path)
        if self.item.kind == EPISODE:
            season, episode = self.season_edit.value(), self.episode_edit.value()
            episode_title, episode_overview = "", ""
            if candidate.kind == SERIES:
                # Nur bei einer echten Serie gibt es ueberhaupt Staffel-/
                # Episodendaten abzufragen - ein manuell gewaehlter Film
                # (z. B. ein bei TMDb als Film katalogisiertes Special)
                # liefert stattdessen nur Titel/Beschreibung des Films.
                ep_info = provider.episode(candidate.external_id, season, episode)
                episode_title = ep_info.title if ep_info else ""
                episode_overview = ep_info.overview if ep_info else ""
            if not episode_title:
                parsed = parse_episode(path)
                episode_title = parsed.guessed_title if parsed else ""
            self.library.set_match(
                path, info, candidate.score, STATUS_MATCHED, season=season,
                episode=episode, episode_title=episode_title,
                episode_overview=episode_overview,
                note=_("von Hand zugeordnet"))
        else:
            self.library.set_match(path, info, candidate.score, STATUS_MATCHED,
                                   note=_("von Hand zugeordnet"))
        self.accept()
