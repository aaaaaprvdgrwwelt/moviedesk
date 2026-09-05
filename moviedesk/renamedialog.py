"""Vorschau der geplanten Umbenennungen - nichts geschieht ohne "Anwenden"."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QHeaderView, QLabel,
    QMessageBox, QProgressDialog, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from . import renamer
from .i18n import _
from .library import LibraryIndex

WARN_BG = QColor(214, 154, 40, 60)
NOTE_BG = QColor(60, 130, 200, 40)


class RenameDialog(QDialog):
    def __init__(self, ops: list[renamer.RenameOp], library: LibraryIndex,
                unchanged: int, parent=None):
        super().__init__(parent)
        self.ops = ops
        self.library = library
        self.setWindowTitle(_("Umbenennen …"))
        self.resize(900, 500)

        info = QLabel(
            _("{n} Aenderung(en) geplant, {u} bereits korrekt benannt.").format(
                n=len(ops), u=unchanged))

        self.table = QTableWidget(len(ops), 3)
        self.table.setHorizontalHeaderLabels(
            [_("Bisher"), _("Neu"), _("Status")])
        # Interactive statt Stretch: lange Pfade duerfen breiter als das
        # Fenster sein, dafuer erscheint dann eine horizontale Bildlaufleiste
        # statt den Text abzuschneiden.
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)

        for row, op in enumerate(ops):
            old_item = QTableWidgetItem(str(op.old))
            old_item.setFlags(
                (old_item.flags() | Qt.ItemIsUserCheckable)
                & ~Qt.ItemIsEditable)
            old_item.setCheckState(
                Qt.Checked if op.selected and op.status == "ok" else Qt.Unchecked)
            if op.status == "conflict":
                old_item.setFlags(old_item.flags() & ~Qt.ItemIsUserCheckable)

            new_item = QTableWidgetItem(str(op.new))
            if op.status == "conflict":
                status_text = op.reason
            elif op.warning:
                status_text = _("wird umbenannt") + " - " + op.warning
            else:
                status_text = _("wird umbenannt")
            status_item = QTableWidgetItem(status_text)

            if op.status == "conflict":
                for item in (old_item, new_item, status_item):
                    item.setBackground(WARN_BG)
            elif op.warning:
                for item in (old_item, new_item, status_item):
                    item.setBackground(NOTE_BG)

            self.table.setItem(row, 0, old_item)
            self.table.setItem(row, 1, new_item)
            self.table.setItem(row, 2, status_item)

        self.table.resizeColumnsToContents()

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.apply_button = buttons.addButton(
            _("Anwenden"), QDialogButtonBox.AcceptRole)
        self.apply_button.setEnabled(
            any(op.status == "ok" for op in ops))
        buttons.accepted.connect(self._apply)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(info)
        layout.addWidget(self.table, 1)
        layout.addWidget(buttons)

    def _apply(self) -> None:
        for row, op in enumerate(self.ops):
            item = self.table.item(row, 0)
            op.selected = item.checkState() == Qt.Checked

        selected = [op for op in self.ops if op.selected and op.status == "ok"]
        # Diesen Dialog ausblenden, bevor der Fortschrittsdialog seine eigene
        # verschachtelte Ereignisschleife startet - zwei gleichzeitig aktive,
        # sich ueberlappende Fenster-Neuzeichnungen (dieser Dialog + die
        # Fortschrittsanzeige) haben in der Praxis zu Abstuerzen beim
        # Neuzeichnen gefuehrt.
        self.hide()
        progress = QProgressDialog(
            _("Benenne um …"), None, 0, len(selected), self.parent())
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setCancelButton(None)
        # Sonst schliesst sich die Anzeige schon beim letzten Element, weil
        # der Fortschritt vor der eigentlichen Arbeit daran gemeldet wird.
        progress.setAutoClose(False)
        progress.setAutoReset(False)

        thread, worker = renamer.run_in_thread(self.ops, self.library)
        worker.progress.connect(lambda i, n, name: (
            progress.setMaximum(n), progress.setValue(i), progress.setLabelText(name)))
        worker.finished.connect(self._on_finished)
        thread.finished.connect(progress.close)
        self._thread, self._worker = thread, worker
        thread.start()
        progress.exec()
        thread.wait(5000)

    def _on_finished(self, results: list) -> None:
        errors = [(op, err) for op, err in results if err]
        ok_count = len(results) - len(errors)
        if errors:
            detail = "\n".join(f"{op.old.name}: {err}" for op, err in errors)
            QMessageBox.warning(
                self, _("Umbenennen …"),
                _("{ok} erfolgreich, {failed} fehlgeschlagen:\n{detail}").format(
                    ok=ok_count, failed=len(errors), detail=detail))
        else:
            QMessageBox.information(
                self, _("Umbenennen …"),
                _("{ok} Datei(en) umbenannt.").format(ok=ok_count))
        self.accept()
