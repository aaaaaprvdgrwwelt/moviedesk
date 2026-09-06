# Changelog

Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).
Noch kein Release getaggt — alles bislang unter „Unreleased“.

## [Unreleased]

### Added

- Ordner scannen, Metadaten von TMDb/OMDb/TheTVDB holen, Filme/Serien nach
  Vorlage umbenennen.
- Menüleiste und Tastenkürzel, Hilfe-Dialog (`F1`).
- Windows-Installer und macOS-Pakete (PyInstaller + Inno Setup), gebaut in
  CI bei einem Versions-Tag.
- `.desktop`-Eintrag für Quellinstallationen unter Linux
  (`install-desktop.sh`).
- Gezielter Scan nur eines einzelnen Films/einer Serie statt des ganzen
  Wurzelordners (Rechtsklick).
- Erkennung von Mehrfach-Episoden (`S01E01E02`) und Anime-Nummerierung
  ohne Staffelangabe.
- Scan-Fortschrittsdialog mit „Abbrechen“-Knopf.
- Testsuite (pytest) für Parser, Bibliotheksindex und Scanner.
- CI (GitHub Actions): Tests bei jedem Push/PR.
- Projektseite unter `aaaaaprvdgrwwelt.github.io/moviedesk`.

### Changed

- Gemeinsame Bausteine (Sprachumschaltung, Theme, Icons, Programmsymbol,
  Thumbnails, Antwort-Cache, Titel-Ähnlichkeit, Menü-/Kachel-/Listen-
  Mechanismen) nach [deskkit](https://github.com/aaaaaprvdgrwwelt/deskkit)
  ausgelagert — geteilt mit ComicDesk, BookDesk und AudioDesk.

### Security

- API-Schlüssel (TMDb, TheTVDB, OMDb, OpenSubtitles) landen im
  System-Schlüsselbund statt im Klartext in der Konfigurationsdatei.

[Unreleased]: https://github.com/aaaaaprvdgrwwelt/moviedesk/commits/main
