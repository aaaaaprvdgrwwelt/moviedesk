# Pakete bauen

PyInstaller ist kein Cross-Compiler: ein Windows-Programm muss auf Windows
entstehen, ein Mac-Programm auf einem Mac. Deshalb baut
`.github/workflows/release.yml` beides auf GitHubs Rechnern.

## Der übliche Weg

```bash
git tag v0.2.0
git push origin v0.2.0
```

Das genügt. Der Workflow baut Windows, macOS (Apple Silicon) und macOS
(Intel), prüft jedes Paket mit `--selftest` und hängt die Ergebnisse an ein
neues Release.

Zum Ausprobieren ohne Veröffentlichung: **Actions → Pakete bauen → Run
workflow**. Dieselben Dateien liegen danach als Artefakt am Lauf.

## Von Hand, auf der jeweiligen Plattform

```bash
pip install -r requirements.txt pyinstaller
python packaging/make_icons.py packaging      # .ico und .iconset
iconutil -c icns packaging/moviedesk.iconset  # nur auf macOS
pyinstaller packaging/moviedesk.spec --noconfirm --clean
```

Das Ergebnis liegt in `dist/`. Für den Windows-Installer zusätzlich
[Inno Setup](https://jrsoftware.org/isinfo.php):

```
iscc /DVersion=0.2.0 packaging\moviedesk.iss
```

## Signieren

Die Pakete sind **nicht signiert** (siehe die ausführliche Begründung in
`comicdesk/packaging/README.md` - dieselbe gilt hier).
