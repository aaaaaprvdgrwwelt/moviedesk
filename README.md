# MovieDesk

[![Tests](https://github.com/aaaaaprvdgrwwelt/moviedesk/actions/workflows/tests.yml/badge.svg)](https://github.com/aaaaaprvdgrwwelt/moviedesk/actions/workflows/tests.yml)

Ein Dateimanager, der nur Filme und Serien kennt: sichten, Metadaten von
TMDb/OMDb/TheTVDB holen, Untertitel herunterladen, `.nfo`-Dateien für
Kodi/Jellyfin/Plex erzeugen, Ordner und Dateien nach Vorlage umbenennen.
Python + Qt (PySide6), auf demselben
[deskkit](https://github.com/aaaaaprvdgrwwelt/deskkit)-Fundament wie
[ComicDesk](https://github.com/aaaaaprvdgrwwelt/comicdesk),
[BookDesk](https://github.com/aaaaaprvdgrwwelt/bookdesk) und
[AudioDesk](https://github.com/aaaaaprvdgrwwelt/audiodesk). Läuft unter
Linux, Windows und macOS. Oberfläche auf Deutsch und Englisch. Bewusst
schlank gehalten — als übersichtliche Alternative zu
tinyMediaManager/Sonarr/Radarr für eine private Sammlung.

> Status: nutzbar. Entwickelt und getestet unter Linux; Windows und macOS
> sollten funktionieren (reines Qt/Python), sind aber nicht manuell
> getestet — siehe [Bekannte Grenzen](#bekannte-grenzen).

## Installation

### Fertige Pakete (Windows, macOS)

Unter [Releases](https://github.com/aaaaaprvdgrwwelt/moviedesk/releases)
liegen ein Windows-Installer und je ein DMG für Apple Silicon und Intel.
Python muss dafür nicht installiert sein.

Beide sind **nicht signiert** — ein Zertifikat kostet mehr, als ein
kostenloses Projekt ausgeben mag. Deshalb einmalig:

* **Windows:** „Der Computer wurde geschützt“ → *Weitere Informationen* →
  *Trotzdem ausführen*.
* **macOS:** beim ersten Start *Rechtsklick auf MovieDesk → Öffnen*, dann
  im Dialog *Öffnen*. Ein Doppelklick allein wird abgelehnt.

Wie die Pakete entstehen, steht in [packaging/](packaging/README.md).

### Aus dem Quelltext (Linux und alle anderen)

Voraussetzung ist Python 3.10 oder neuer. `deskkit` muss als
Geschwister-Ordner neben `moviedesk/` liegen (siehe `requirements.txt`,
`-e ../deskkit`):

```bash
git clone https://github.com/aaaaaprvdgrwwelt/deskkit.git
git clone https://github.com/aaaaaprvdgrwwelt/moviedesk.git
cd moviedesk
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Starten

```bash
./moviedesk.sh                # oder: .venv/bin/python -m moviedesk
./install-desktop.sh          # Eintrag im Anwendungsmenue und Symbole anlegen (Linux)
```

Unter Windows/macOS entsprechend `.venv\Scripts\python -m moviedesk` bzw.
`.venv/bin/python -m moviedesk`.

## Erste Schritte

1. **Einstellungen …** (`Strg+,`) öffnen und mindestens einen API-Key
   hinterlegen — TMDb allein reicht schon für Filme und Serien. Siehe
   [Metadaten-Quellen](#metadaten-quellen) unten für alle vier Quellen und
   wo es den jeweiligen Key gibt.
2. Über **Ordner hinzufügen …** einen Filme- und/oder Serien-Ordner
   angeben.
3. **Scannen** (`F5`) liest die Ordner ein.
4. **Automatisch zuordnen** (`Strg+T`) sucht Metadaten. Unsichere oder
   fehlgeschlagene Treffer bleiben markiert und lassen sich per
   Doppelklick oder Rechtsklick → *Manuell zuordnen* von Hand nachtragen —
   auch direkt per TMDb-/IMDb-Link oder -ID, wenn die normale Suche nichts
   findet.
5. **Umbenennen …** (`Strg+R`) zeigt eine Vorschau aller geplanten
   Umbenennungen. Es wird **nichts** auf der Platte verändert, bevor dort
   auf *Anwenden* geklickt wird.

## Metadaten-Quellen

Alle vier Quellen sind optional und lassen sich einzeln unter
*Einstellungen → Quellen* bzw. *Untertitel* ein-/ausschalten. API-Keys
landen im System-Schlüsselbund (Windows Credential Locker, macOS
Schlüsselbund, Linux Secret Service/KWallet) statt im Klartext in der
Konfigurationsdatei — ohne verfügbaren Schlüsselbund (z. B. per SSH ohne
grafische Sitzung) fällt das auf Klartext in QSettings zurück.

| Quelle | Wofür | Key nötig? |
|---|---|---|
| **TMDb** (The Movie Database) | Titel, Jahr, Beschreibung, Poster, Genres, Bewertung — für Filme *und* Serien. Ohne diesen Key funktioniert die automatische Zuordnung praktisch nicht. | Ja, kostenlos: Konto auf [themoviedb.org](https://www.themoviedb.org/signup), unter *Einstellungen → API* einen Key vom Typ „Developer“ anlegen, den **API Key (v3 auth)** kopieren (nicht den „API Read Access Token“, das ist v4). |
| **TheTVDB** | Alternative für Serien mit guter Staffel-/Episodenstruktur — sinnvoll als Zweitquelle, wenn TMDb eine Serie nicht oder nur lückenhaft kennt. | Ja, kostenlos: Key im [Dashboard](https://thetvdb.com/auth/register) erzeugen. Nur bei einem persönlichen („Hobbyist“-)Key kommt zusätzlich ein PIN dazu. |
| **OMDb** | Ergänzt nur das IMDb-Rating, wenn TMDb/TheTVDB es nicht mitbringen, und hilft bei der manuellen Zuordnung per IMDb-Link/-ID. | Ja, kostenlos: [omdbapi.com/apikey.aspx](https://www.omdbapi.com/apikey.aspx), Bestätigungslink aus der E-Mail aktivieren. |
| **OpenSubtitles** | Untertitel-Download in den unter Einstellungen festgelegten Sprachen. | Ja: Account + API-Consumer auf [opensubtitles.com](https://www.opensubtitles.com/de/consumers) — ohne Login gilt nur ein sehr kleines Tages-Limit. |

## Funktionen

**Scannen** — durchsucht die konfigurierten Filme-/Serien-Ordner nach
Videodateien (`.mp4 .mkv .avi .mov .m4v .wmv .ts .webm .flv`), erkennt
offensichtliche Samples/Trailer/Extras und sortiert sie aus, außer der
Dateiname enthält selbst eine echte Episodenkennung (z. B. „Extra Large
Medium“ als Episodentitel wird nicht mit einem Bonus-Feature verwechselt).
Ein zweiter Lauf liest nur neue/geänderte Dateien neu ein, verschwundene
Einträge fliegen raus. Der Fortschrittsdialog ist jederzeit über
*Abbrechen* unterbrechbar, ohne bereits vorhandene Bibliothekseinträge zu
verlieren.

**Nur einen Film/eine Serie neu scannen** — Rechtsklick auf einen Film
oder eine Serie → *Nur diesen Film/diese Serie scannen*. Praktisch nach
dem Hinzufügen einzelner neuer Dateien, ohne den ganzen (womöglich sehr
großen) Wurzelordner erneut zu durchsuchen.

**Dateinamen-Erkennung** — deckt gängige Szene-Konventionen ab: `S01E05`,
`1x05`, `Season 01/E05.mkv`, das Jahr in Klammern bei Filmen. Zusätzlich:

* **Mehrfach-Episoden** wie `S01E01E02` oder `S01E01-E02` — beide
  Episodennummern werden erkannt statt nur der ersten, die Anzeige zeigt
  `S01E01E02`.
* **Anime-Nummerierung** ohne Staffelangabe (`[Gruppe] Serie - 05
  [1080p].mkv`) — die letzte plausible Zahl im Dateinamen wird als
  durchlaufende Episode übernommen (Staffel 1 angenommen), bekannte
  Auflösungswerte (720, 1080, …) werden dabei ausdrücklich nicht als
  Episodennummer missverstanden.

Was sich nicht sicher erkennen lässt, landet unauffällig im
Match-Dialog statt falsch automatisch zugeordnet zu werden.

**Automatisch zuordnen** — baut aus Dateiname und vorhandenen Angaben eine
Suchanfrage, bewertet jeden Kandidaten nach Titel-Ähnlichkeit und
(sofern bekannt) Jahr, übernimmt ab dem eingestellten Schwellwert
automatisch. Alles darunter erscheint als „unsicher“, **ohne** die Datei
anzufassen. Der Lauf ist über den Fortschrittsdialog abbrechbar.

**Episoden-Tabelle** — sortierbar nach jeder Spalte (z. B. nach Dateiname),
Klick auf den Spaltenkopf.

**Sammlungen** — Filme, die TMDb einer Filmreihe zuordnet (z. B. „Alien
Collection“), werden automatisch gruppiert und links im Filme-Tab
auswählbar. Zusätzlich lassen sich per Rechtsklick eigene Sammlungen
anlegen, die ein erneuter Abgleich nie überschreibt.

**Fehlende Teile** (`Strg+M`) — zeigt bei einer ausgewählten TMDb-Sammlung
oder Serie an, welche Filme bzw. Episoden laut TMDb noch fehlen (dafür ist
ein TMDb-Key nötig). Über *Einstellungen → Allgemein* lässt sich das auf
bereits veröffentlichte/ausgestrahlte Teile beschränken, mit
Ländercode für das Veröffentlichungsdatum bei Filmen.

**Umbenennen …** (`Strg+R`) — Vorschau vor jeder Änderung, frei
einstellbare Vorlagen unter *Einstellungen → Umbenennen*:

* Filme: `{title} {year} {ext}`
* Serien: `{series} {year} {season} {episode} {episode_end} {episode_title}
  {ext}` — `{year}` ist das Jahr der Erstausstrahlung der Serie,
  `{episode_end}` nur bei Mehrteilern wie `S01E01E02` belegt (sonst leer).

Ein `/` in der Vorlage legt eine neue Ordnerebene an. Enthält ein Titel
selbst ungültige Zeichen (z. B. einen Schrägstrich bei einer Doppelfolge),
werden die automatisch unschädlich gemacht — die Vorschau zeigt das mit
einem Hinweis an.

**NFO erzeugen** — schreibt Kodi-/Jellyfin-/Plex-kompatible `.nfo`-Dateien
neben die Videos (bei Serien zusätzlich eine `tvshow.nfo` im
Serienordner), nur auf Wunsch. Optional zusätzlich ein lokales
`poster.jpg` neben der Datei (für Mediacenter ohne Internetzugriff).

**Untertitel herunterladen** — sucht fehlende Untertitel über
OpenSubtitles in den konfigurierten Sprachen und lädt den Treffer mit den
meisten Downloads herunter.

**Löschen** — verschiebt Dateien in den Papierkorb, nichts wird endgültig
gelöscht. „Ganzes Verzeichnis löschen“ ist deaktiviert, wenn die Datei
direkt im Bibliotheksordner liegt, damit sich der Bibliotheksordner selbst
nicht aus Versehen leeren lässt.

**Bibliothek sichern …** — kopiert die Datenbank mit allen Zuordnungen an
einen selbst gewählten Ort (über SQLites Online-Backup-API, sicher auch
während die App läuft). Sie ist die einzige Quelle der Wahrheit für
Zuordnungen; ohne Sicherung wäre ein Datenverlust nicht rückgängig zu
machen.

**Bedienung** — Menüleiste mit allen Befehlen, Werkzeugleiste für die
ständig gebrauchten. Tastenkürzel:

| Kürzel | Aktion |
|---|---|
| `F5` | Scannen |
| `Strg+T` | Automatisch zuordnen |
| `Strg+M` | Fehlende Teile … |
| `Strg+R` | Umbenennen … |
| `Strg+F` | Suchen |
| `Entf` | Löschen … |
| `Strg+,` | Einstellungen … |
| `F1` | Hilfe … |
| `Strg+Q` | Beenden |

## Wo Daten liegen

| Was | Wo |
|---|---|
| Einstellungen | `~/.config/moviedesk/moviedesk.conf` |
| API-Keys | System-Schlüsselbund (Fallback: Klartext in obiger Datei) |
| Bibliotheksindex (Zuordnungen) | `~/.local/share/moviedesk/library.sqlite` |
| Antwort-Cache, Poster | `~/.cache/moviedesk/` |

Der Bibliotheksindex ist — anders als bei ComicDesk, wo die Wahrheit in
`ComicInfo.xml` in der Datei selbst steht — die Quelle der Wahrheit für
Zuordnungen, da Videodateien kein verbreitetes eingebettetes
Metadatenformat kennen. Beim Umbenennen wird der gespeicherte Pfad
automatisch mitgeführt.

## Aufbau

- `moviedesk/parser.py` — Dateinamen zerlegen: Titel, Jahr, Staffel/Episode,
  Mehrfach-Episoden, Anime-Fallback, Sample/Extra-Erkennung
- `moviedesk/scanner.py` — Ordner einlesen (voller Scan und gezielter
  Scan eines einzelnen Films/einer Serie), beides abbrechbar
- `moviedesk/library.py` — SQLite-Bibliotheksindex, Gruppierung nach
  Serie/Sammlung (case-insensitiv)
- `moviedesk/matcher.py` — Kandidaten sammeln und bewerten
- `moviedesk/providers/` — `tmdb.py`, `tvdb.py`, `omdb.py` hinter einer
  gemeinsamen Schnittstelle (`base.py`)
- `moviedesk/subtitles.py` — OpenSubtitles-Client
- `moviedesk/nfo.py` — `.nfo`-Erzeugung
- `moviedesk/renamer.py`/`renamedialog.py` — Vorlagen-Umbenennung
- `moviedesk/mainwindow.py` — Hauptfenster, Kachel-/Tabellenansicht
- `moviedesk/config.py` — Einstellungen (QSettings + Schlüsselbund)
- `moviedesk/i18n.py` — Übersetzungstabelle

## Entwickeln

```bash
.venv/bin/pip install -r requirements-dev.txt
QT_QPA_PLATFORM=offscreen .venv/bin/pytest
```

Windows-Installer und macOS-Pakete entstehen per PyInstaller + Inno Setup
in CI, ausgelöst von einem Tag wie `v0.2.0` — siehe
[packaging/README.md](packaging/README.md).

## Bekannte Grenzen

- Windows/macOS sind reines Qt/Python und sollten funktionieren, wurden
  aber nicht manuell auf diesen Plattformen getestet (nur die
  automatisierte Testsuite läuft auch dort in der CI).
- Dateinamen-Erkennung deckt gängige Szene-Konventionen und die üblichen
  Anime-Fallbacks ab, aber nicht jeden Sonderfall — unsichere/nicht
  erkannte Dateien landen im Match-Dialog statt falsch zugeordnet zu
  werden.
- Kein Drag & Drop aus anderen Dateimanagern.

## Lizenz

[MIT](LICENSE). Verwendet [PySide6](https://doc.qt.io/qtforpython/) (LGPL),
[Pillow](https://python-pillow.org/) (MIT-CMU),
[Send2Trash](https://github.com/arsenetar/send2trash) (BSD) und
[keyring](https://github.com/jaraco/keyring) (MIT). Metadaten stammen von
[TMDb](https://www.themoviedb.org/), [TheTVDB](https://thetvdb.com/),
[OMDb](https://www.omdbapi.com/) und [OpenSubtitles](https://www.opensubtitles.com/).
