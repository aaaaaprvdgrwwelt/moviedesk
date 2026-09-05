"""MovieDesk - Dateimanager fuer Filme und Serien."""
from __future__ import annotations

import sys

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from deskkit import theme
from .appicon import icon as app_icon
from .i18n import set_language
from .mainwindow import MainWindow


def selftest() -> int:
    """Kurzer Start ohne Fenster - fuer die Pruefung fertiger Pakete."""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication(sys.argv[:1])
    theme.apply(app)
    app.setWindowIcon(app_icon())
    from .providers.tmdb import TMDbProvider

    window = MainWindow()
    window.close()
    provider = TMDbProvider("")
    ok, _why = provider.available()
    print("Qt: ok")
    print(f"TMDb-Provider geladen: {'ok' if not ok else 'unerwartet verfuegbar'}")
    print("Selbsttest bestanden.")
    return 0


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
