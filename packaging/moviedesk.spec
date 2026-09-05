# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-Bauplan fuer Windows und macOS.

Aufruf aus dem Projektordner:

    pyinstaller packaging/moviedesk.spec --noconfirm
"""
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

HIER = Path(SPECPATH).resolve()
WURZEL = HIER.parent
#: deskkit liegt als Geschwister-Repo daneben und wird per "pip install -e"
#: eingebunden (siehe requirements.txt) - PyInstallers statische Analyse
#: folgt dem editable-Import-Hook nicht von selbst, deshalb Quellordner und
#: Submodule hier ausdruecklich mitgeben.
DESKKIT = WURZEL.parent / "deskkit"

datas = [(str(WURZEL / "moviedesk" / "assets"), "moviedesk/assets")]

hiddenimports = [
    "PIL._avif",              # AVIF steckt in einer Erweiterung, nicht im Code
]
hiddenimports += collect_submodules("moviedesk")
hiddenimports += collect_submodules("deskkit")

block_cipher = None

a = Analysis(
    [str(HIER / "entry.py")],
    pathex=[str(WURZEL), str(DESKKIT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # Qt bringt viel mit, was ein Videodateimanager nie braucht. Das spart
    # rund 100 MB im fertigen Paket.
    excludes=[
        "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
        "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtDataVisualization",
        "PySide6.QtMultimedia", "PySide6.QtBluetooth", "PySide6.QtSensors",
        "PySide6.QtDesigner", "PySide6.QtTest",
        "tkinter", "unittest", "pydoc_data",
    ],
    noarchive=False,
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MovieDesk",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,           # kein Konsolenfenster beim Start
    icon=str(HIER / "moviedesk.ico") if sys.platform == "win32" else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="MovieDesk",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="MovieDesk.app",
        icon=str(HIER / "moviedesk.icns"),
        bundle_identifier="de.moviedesk.MovieDesk",
        info_plist={
            "CFBundleName": "MovieDesk",
            "CFBundleDisplayName": "MovieDesk",
            "NSHighResolutionCapable": True,
            # Ohne das startet die App auf Deutsch nur zufaellig richtig.
            "CFBundleDevelopmentRegion": "de",
            "CFBundleDocumentTypes": [{
                "CFBundleTypeName": "Video",
                "CFBundleTypeRole": "Viewer",
                "LSItemContentTypes": ["public.movie"],
            }],
        },
    )
