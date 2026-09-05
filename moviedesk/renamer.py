"""Zielpfade aus Vorlagen bauen und Umbenennungsplaene ausfuehren.

Reine Planung ist von der Ausfuehrung getrennt: `build_plan` fasst nur an,
was auf dem Papier passieren soll; erst `apply` ruehrt das Dateisystem an -
und auch das nur fuer die vom Nutzer bestaetigten Eintraege.
"""
from __future__ import annotations

import glob
import re
import shutil
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from .i18n import _
from .library import Item, LibraryIndex, MOVIE, STATUS_MATCHED

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

#: Begleitdateien mit demselben Namensstamm wie das Video - wandern beim
#: Umbenennen automatisch mit (NFO fuer Kodi/Jellyfin, Untertitel).
SIDECAR_EXTENSIONS = (".nfo", ".srt", ".sub", ".ass", ".vtt", ".idx")


def sanitize_segment(text: str) -> str:
    """Ein Pfadsegment plattformsicher machen - auch unter Linux/Mac, falls
    die Bibliothek spaeter auf ein Windows-Dateisystem synchronisiert wird."""
    text = _INVALID.sub("", text).strip()
    text = text.rstrip(". ")
    return text or "_"


@dataclass
class RenameOp:
    old: Path
    new: Path
    kind: str
    #: Bibliotheksordner, in dem die Datei liegt - Grenze fuers Aufraeumen
    #: leer gewordener alter Ordner nach dem Verschieben (siehe `apply`).
    root: Path = field(default_factory=Path)
    status: str = "ok"          # ok | same | conflict
    reason: str = ""
    #: Hinweis (kein Konflikt) - z. B. wenn ein Titel einen Schraegstrich
    #: enthielt und deshalb bereinigt wurde. Nur zur Information.
    warning: str = ""
    selected: bool = True


_DOUBLE_DASH = re.compile(r"\s*-\s*-\s*")
_TRAILING_DASH = re.compile(r"\s*-\s*$")
_EMPTY_PARENS = re.compile(r"\s*\(\s*\)")
_PATH_BREAKER = re.compile(r"[/\\]+")


def _safe_value(text) -> str:
    """Schraegstriche in eingesetzten Werten (Titel, Episodentitel, ...)
    unschaedlich machen - sonst zerlegt der Pfadaufbau einen Titel wie
    "Loreleis Tod/Der Verdaechtige" faelschlich in einen Extra-Ordner,
    weil `/` sonst mit dem `/` der Vorlage selbst verwechselt wird."""
    return _PATH_BREAKER.sub(" - ", str(text))


def _clean_empty_tokens(formatted: str) -> str:
    """Trenner entfernen, die ein leerer Platzhalter uebrig laesst - z. B.
    " - " vor der Endung ohne Episodentitel, oder "()" ohne bekanntes Jahr."""
    parts = []
    for part in formatted.split("/"):
        part = _EMPTY_PARENS.sub("", part)
        part = _DOUBLE_DASH.sub(" - ", part)
        part = _TRAILING_DASH.sub("", part)
        parts.append(part)
    return "/".join(parts)


def build_movie_target(root: Path, item: Item, template: str) -> Path:
    ext = Path(item.path).suffix
    formatted = template.format(
        title=_safe_value(item.title or _("Unbekannt")),
        year=item.year or "", ext="")
    formatted = _clean_empty_tokens(formatted)
    segments = [sanitize_segment(s) for s in formatted.split("/") if s.strip()]
    segments[-1] += ext
    return root.joinpath(*segments)


def build_episode_target(root: Path, item: Item, template: str) -> Path | None:
    if item.season is None or item.episode is None:
        return None
    ext = Path(item.path).suffix
    formatted = template.format(
        series=_safe_value(item.title or _("Unbekannt")), year=item.year or "",
        season=item.season, episode=item.episode,
        episode_end=item.episode_end if item.episode_end is not None else "",
        episode_title=_safe_value(item.episode_title or ""), ext="")
    formatted = _clean_empty_tokens(formatted)
    segments = [sanitize_segment(s) for s in formatted.split("/") if s.strip()]
    segments[-1] += ext
    return root.joinpath(*segments)


def _title_warning(*raw_values: str) -> str:
    """Hinweistext, wenn ein Rohwert Zeichen enthielt, die im Dateinamen
    nicht so stehen bleiben konnten (v. a. ein Schraegstrich im Titel -
    z. B. bei Doppelfolgen wie "Teil 1/Teil 2")."""
    for value in raw_values:
        if value and _PATH_BREAKER.search(value):
            return _("Titel enthielt einen Schraegstrich - wurde durch "
                     "\" - \" ersetzt.")
    for value in raw_values:
        if value and _INVALID.search(value):
            return _("Titel enthielt Zeichen, die im Dateinamen nicht "
                     "erlaubt sind - wurden entfernt.")
    return ""


def build_plan(items: list[Item], movie_template: str,
              series_template: str) -> list[RenameOp]:
    """Nur zugeordnete Dateien werden geplant - unsichere/nicht zugeordnete
    Treffer sollen den Nutzer erst ueber den Match-Dialog passieren."""
    ops: list[RenameOp] = []
    for item in items:
        if item.status != STATUS_MATCHED:
            continue
        root = Path(item.root)
        old = Path(item.path)
        if item.kind == MOVIE:
            new = build_movie_target(root, item, movie_template)
            warning = _title_warning(item.title or "")
        else:
            new = build_episode_target(root, item, series_template)
            if new is None:
                continue
            warning = _title_warning(item.title or "", item.episode_title or "")
        status = "same" if new == old else "ok"
        ops.append(RenameOp(old, new, item.kind, root=root, status=status,
                            warning=warning))

    targets = Counter(op.new for op in ops if op.status != "same")
    for op in ops:
        if op.status == "same":
            continue
        if targets[op.new] > 1:
            op.status, op.reason = "conflict", _("Mehrere Dateien wollen dasselbe Ziel.")
        elif op.new.exists():
            op.status, op.reason = "conflict", _("Zieldatei existiert bereits.")
    return ops


def _move_sidecars(old: Path, new: Path) -> None:
    """Dateien mit gleichem Namensstamm (NFO, Untertitel) mitverschieben.

    Erfasst auch Varianten mit Sprachcode wie "Film.de.srt": alles nach dem
    alten Namensstamm wird unveraendert an den neuen Stamm angehaengt.
    """
    if not old.parent.is_dir():
        return
    pattern = glob.escape(old.stem) + "*"
    for candidate in old.parent.glob(pattern):
        if candidate == old or candidate.suffix.lower() not in SIDECAR_EXTENSIONS:
            continue
        extra = candidate.name[len(old.stem):]
        target = new.parent / f"{new.stem}{extra}"
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(candidate), str(target))
        except OSError:
            pass  # die Hauptdatei ist schon umbenannt - Begleitdatei ist nicht kritisch


def _cleanup_empty_dirs(folder: Path, root: Path) -> None:
    """Leer gewordene alte Ordner (z. B. der bisherige Serien-/Staffelordner)
    nach oben hin entfernen - nie ueber die Bibliotheksordner-Wurzel hinaus."""
    try:
        root = root.resolve()
        current = folder.resolve()
    except OSError:
        return
    while current != root and root in current.parents:
        try:
            next(current.iterdir())
            return  # noch etwas drin - hier aufhoeren
        except StopIteration:
            pass
        except OSError:
            return
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def _apply_one(op: RenameOp, library: LibraryIndex) -> str | None:
    """Eine Umbenennung ausfuehren. None bei Erfolg, sonst die Fehlermeldung."""
    try:
        op.new.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(op.old), str(op.new))
        library.update_path(op.old, op.new)
        _move_sidecars(op.old, op.new)
        if op.root != Path():
            _cleanup_empty_dirs(op.old.parent, op.root)
        return None
    except OSError as exc:
        return str(exc)


def apply(ops: Iterable[RenameOp],
         library: LibraryIndex) -> list[tuple[RenameOp, str | None]]:
    """Fuehrt nur ausgewaehlte, konfliktfreie Eintraege aus - synchron.

    Fuer viele Dateien besser `run_in_thread` verwenden, damit die
    Oberflaeche waehrenddessen nicht einfriert.
    """
    results: list[tuple[RenameOp, str | None]] = []
    for op in ops:
        if not op.selected or op.status != "ok":
            continue
        results.append((op, _apply_one(op, library)))
    return results


class RenameWorker(QObject):
    """Laeuft im eigenen Thread - bei vielen Dateien (grosse Ordner, langsame
    externe Laufwerke) soll die Oberflaeche dabei nicht einfrieren."""

    progress = Signal(int, int, str)
    finished = Signal(list)   # list[tuple[RenameOp, str | None]]

    def __init__(self, ops: list[RenameOp], library: LibraryIndex):
        super().__init__()
        self.ops = [op for op in ops if op.selected and op.status == "ok"]
        self.library = library

    def run(self) -> None:
        results: list[tuple[RenameOp, str | None]] = []
        total = len(self.ops)
        for i, op in enumerate(self.ops, 1):
            self.progress.emit(i, total, op.new.name)
            results.append((op, _apply_one(op, self.library)))
        self.finished.emit(results)


def run_in_thread(ops: list[RenameOp], library: LibraryIndex):
    """Gibt (thread, worker) zurueck - der Aufrufer verbindet die Signale."""
    thread = QThread()
    worker = RenameWorker(ops, library)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    return thread, worker
