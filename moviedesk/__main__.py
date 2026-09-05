"""MovieDesk - Dateimanager fuer Filme und Serien."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from deskkit import theme
from .appicon import icon as app_icon
from .i18n import set_language
from .mainwindow import MainWindow


def selftest() -> int:
    """Kurzer Start ohne Fenster - fuer die Pruefung fertiger Pakete.

    Ein Paket, dem eine Bibliothek fehlt, stuerzt sonst erst beim Nutzer ab.
    Hier faellt es beim Bauen auf. Ohne Konsolenfenster (Windows/macOS-Paket)
    schreibt PyInstaller keine Ausgabe an - deshalb zusaetzlich in eine Datei.
    """
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    zeilen: list[str] = []

    def sag(text: str) -> None:
        zeilen.append(text)
        print(text)

    app = QApplication(sys.argv[:1])
    theme.apply(app)
    app.setWindowIcon(app_icon())
    from .providers.tmdb import TMDbProvider

    window = MainWindow()
    window.close()
    provider = TMDbProvider("")
    ok, _why = provider.available()
    try:
        from PIL import Image  # noqa: F401
        pillow_ok = True
    except Exception:  # noqa: BLE001
        pillow_ok = False
    sag("Qt: ok")
    sag(f"TMDb-Provider geladen: {'ok' if not ok else 'unerwartet verfuegbar'}")
    sag(f"Pillow (Poster-Miniaturen): {'ok' if pillow_ok else 'FEHLT'}")
    fehlt = [] if pillow_ok else ["Pillow"]
    sag("Fehlt: " + ", ".join(fehlt) if fehlt else "Selbsttest bestanden.")
    try:
        Path("selftest.log").write_text("\n".join(zeilen) + "\n", "utf-8")
    except OSError:
        pass
    return 1 if fehlt else 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    app = QApplication(sys.argv)
    app.setApplicationName("MovieDesk")
    app.setOrganizationName("moviedesk")
    set_language(QSettings("moviedesk", "moviedesk").value("language", "auto"))
    theme.apply(app)
    app.setWindowIcon(app_icon())
    app.setDesktopFileName("moviedesk")
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
