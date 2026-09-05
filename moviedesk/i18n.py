"""Sprachumschaltung.

Die Quelltext-Strings sind zugleich die Schluessel. Sie sind ASCII-Deutsch
gehalten, damit sie robust als Schluessel taugen; die Tabelle liefert fuer
`de` das korrekt umlautete Deutsch und fuer `en` die Uebersetzung. Fehlt ein
Eintrag, wird der Schluessel selbst angezeigt - die App bleibt also immer
benutzbar, auch wenn eine Uebersetzung vergessen wurde.
"""
from __future__ import annotations

#: Code -> Anzeigename im Menue.
LANGUAGES = {"auto": "Automatisch", "de": "Deutsch", "en": "English"}

_current = "de"


def system_language() -> str:
    from PySide6.QtCore import QLocale

    code = QLocale.system().name().split("_")[0].lower()
    return code if code in ("de", "en") else "en"


def set_language(code: str) -> None:
    global _current
    _current = system_language() if code == "auto" else (
        code if code in ("de", "en") else "de")


def language() -> str:
    return _current


def _(text: str) -> str:
    """Uebersetzt `text` in die aktive Sprache."""
    return TABLE.get(_current, {}).get(text, text)


# ---------------------------------------------------------------------------
DE = {
    # Nur Eintraege, bei denen der ASCII-Schluessel Umlaute braucht.
    "Loeschen": "Löschen",
    "Ordner hinzufuegen …": "Ordner hinzufügen …",
    "Ordner waehlen": "Ordner wählen",
    "Bitte mindestens einen Ordner hinzufuegen.":
        "Bitte mindestens einen Ordner hinzufügen.",
    "Bitte mindestens eine Datei waehlen.": "Bitte mindestens eine Datei wählen.",
    "Bitte genau einen Eintrag waehlen.": "Bitte genau einen Eintrag wählen.",
    "Waehlen …": "Wählen …",
    "Einstellungen …": "Einstellungen …",
    "Automatisch zuordnen": "Automatisch zuordnen",
    "Umbenennen …": "Umbenennen …",
    "Groesse": "Größe",
    "unter Schwellwert {threshold}. {notes}": "unter Schwellwert {threshold}. {notes}",
    "Kein API-Key hinterlegt.": "Kein API-Key hinterlegt.",
    "Titel-Aehnlichkeit {value}": "Titel-Ähnlichkeit {value}",
    "ergaenzt durch {sources}": "ergänzt durch {sources}",
    "Nicht konfiguriert": "Nicht konfiguriert",
    "ueberspringen": "überspringen",
    "Uebernehmen": "Übernehmen",
    "Schliessen": "Schließen",
    "Zurueck": "Zurück",
    "Ueberschreiben": "Überschreiben",
    "Kein Eintrag ausgewaehlt": "Kein Eintrag ausgewählt",
    "Tages-Limit fuer Untertitel-Downloads erreicht.":
        "Tages-Limit für Untertitel-Downloads erreicht.",
    "Treffer waehlen": "Treffer wählen",
    "Aktiv (nur IMDb-Rating ergaenzen)": "Aktiv (nur IMDb-Rating ergänzen)",
    "Schwellwert fuer automatische Zuordnung":
        "Schwellwert für automatische Zuordnung",
    "Staffel waehlen": "Staffel wählen",
    "Loeschen …": "Löschen …",
    "Datei nicht gefunden - eventuell verschoben oder geloescht.":
        "Datei nicht gefunden - eventuell verschoben oder gelöscht.",
    "Staffel von Hand geaendert": "Staffel von Hand geändert",
    "Serie von Hand geaendert": "Serie von Hand geändert",
    "Keine zugeordneten Dateien ausgewaehlt.":
        "Keine zugeordneten Dateien ausgewählt.",
    "Vollstaendig - alle Filme dieser Reihe sind vorhanden.":
        "Vollständig - alle Filme dieser Reihe sind vorhanden.",
    "Diese Serie ist nicht ueber TMDb zugeordnet.":
        "Diese Serie ist nicht über TMDb zugeordnet.",
    "Vollstaendig - alle Episoden sind vorhanden.":
        "Vollständig - alle Episoden sind vorhanden.",
    "Zu Sammlung hinzufuegen …": "Zu Sammlung hinzufügen …",
    "Nur bereits veroeffentlichte/ausgestrahlte fehlende Teile anzeigen":
        "Nur bereits veröffentlichte/ausgestrahlte fehlende Teile anzeigen",
    "Laendercode (Filme)": "Ländercode (Filme)",
    "Laendercode gilt nur fuer Filme (TMDb kennt laenderspezifische "
    "Kinostarts); bei Episoden gibt es bei TMDb nur ein einziges "
    "weltweites Ausstrahlungsdatum.":
        "Ländercode gilt nur für Filme (TMDb kennt länderspezifische "
        "Kinostarts); bei Episoden gibt es bei TMDb nur ein einziges "
        "weltweites Ausstrahlungsdatum.",
    "Nichts fehlt - vollstaendig.": "Nichts fehlt - vollständig.",
}
EN: dict[str, str] = {}

TABLE = {"de": DE, "en": EN}
