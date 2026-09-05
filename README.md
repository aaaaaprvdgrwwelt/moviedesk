# MovieDesk

Ein Dateimanager, der nur Filme und Serien kennt: sichten, Metadaten von
TMDb/OMDb/TheTVDB holen, Ordner und Dateien nach Vorlage umbenennen. Python +
Qt (PySide6), läuft unter Linux, Windows und macOS. Bewusst schlank gehalten -
als übersichtliche Alternative zu tinyMediaManager/Sonarr.

> Status: erste nutzbare Fassung, ungetestet außerhalb von Linux.

## Installation

Voraussetzung ist Python 3.10 oder neuer.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Starten

```bash
./moviedesk.sh
```

Unter Windows/macOS entsprechend `.venv\Scripts\python -m moviedesk` bzw.
`.venv/bin/python -m moviedesk`.

## Erste Schritte

1. **Einstellungen …** öffnen und mindestens einen API-Key hinterlegen
   (TMDb reicht für Filme und Serien; OMDb ergänzt nur das IMDb-Rating;
   TheTVDB ist eine alternative Quelle für Serien).
2. Über **Ordner hinzufügen …** einen Filme- und/oder Serien-Ordner
   angeben.
3. **Scannen** liest die Ordner ein.
4. **Automatisch zuordnen** sucht Metadaten; unsichere Treffer bleiben
   als "unsicher" markiert und lassen sich per Doppelklick von Hand
   zuordnen.
5. **Umbenennen …** zeigt eine Vorschau aller geplanten Umbenennungen.
   Es wird **nichts** auf der Platte verändert, bevor hier auf
   "Anwenden" geklickt wird.

## Wo Daten liegen

| Was | Wo |
|---|---|
| Einstellungen | `~/.config/moviedesk/moviedesk.conf` |
| Bibliotheksindex (Zuordnungen) | `~/.local/share/moviedesk/library.sqlite` |
| Antwort-Cache, Poster | `~/.cache/moviedesk/` |

Der Bibliotheksindex ist - anders als bei comicdesk, wo die Wahrheit in
`ComicInfo.xml` in der Datei steht - die Quelle der Wahrheit für
Zuordnungen, da Videodateien kein verbreitetes eingebettetes
Metadatenformat kennen. Beim Umbenennen wird der gespeicherte Pfad
automatisch mitgeführt.

## Bekannte Grenzen (erste Fassung)

- Keine `.nfo`-Erzeugung für Kodi/Jellyfin/Plex.
- Keine fertigen Installer/Pakete - nur Start aus dem Quelltext.
- Erkennung von Dateinamen deckt gängige Szene-Konventionen ab, aber
  nicht jeden Sonderfall - unsichere/nicht erkannte Dateien landen
  einfach im Match-Dialog statt falsch automatisch zugeordnet zu werden.
