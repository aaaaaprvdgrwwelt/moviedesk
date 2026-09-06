"""Hilfe: was moviedesk kann und wie man an die noetigen API-Keys kommt."""
from __future__ import annotations

from deskkit.helpdialog import HelpDialog as _HelpDialog

from .i18n import _

HELP_HTML = """
<h2>Erste Schritte</h2>
<ol>
<li>Unter <b>Einstellungen</b> mindestens einen API-Key hinterlegen (siehe unten) -
    TMDb allein reicht schon fuer Filme und Serien.</li>
<li>Ueber <b>Ordner hinzufuegen</b> einen Filme- und/oder Serien-Ordner angeben.</li>
<li><b>Scannen</b> liest die Ordner ein.</li>
<li><b>Automatisch zuordnen</b> sucht Metadaten. Unsichere oder fehlgeschlagene
    Treffer bleiben markiert und lassen sich per Doppelklick oder Rechtsklick
    &rarr; <i>Manuell zuordnen</i> von Hand nachtragen.</li>
<li><b>Umbenennen</b> zeigt eine Vorschau aller geplanten Aenderungen. Es wird
    nichts auf der Platte veraendert, bevor dort auf <i>Anwenden</i> geklickt wird.</li>
</ol>

<h2>Welche API-Keys wofuer?</h2>
<p>Alle Quellen sind optional und lassen sich einzeln unter
<b>Einstellungen &rarr; Quellen</b> bzw. <b>Untertitel</b> ein- und ausschalten.
Nur TMDb wird fuer die meisten Funktionen empfohlen - der Rest ergaenzt oder
springt ein, wenn TMDb etwas nicht kennt.</p>

<h3>TMDb (The Movie Database) - empfohlen, deckt Filme und Serien ab</h3>
<p>Liefert Titel, Jahr, Beschreibung, Poster, Genres, Bewertung - fuer Filme
und Serien gleichermassen. Ohne diesen Key funktioniert die automatische
Zuordnung praktisch nicht.</p>
<ol>
<li>Kostenloses Konto auf <a href="https://www.themoviedb.org/signup">themoviedb.org</a> anlegen.</li>
<li>Unter <b>Einstellungen &rarr; API</b> auf <i>Create</i> klicken, als Typ
    <b>Developer</b> waehlen (kostenlos, nicht kommerziell).</li>
<li>Ein kurzes Formular ausfuellen (Anwendungsname, URL, Zusammenfassung) -
    wird nicht ernsthaft geprueft, bei privater Nutzung reicht z. B.
    "Persoenliches Tool zum Organisieren meiner Mediathek, nicht kommerziell."</li>
<li>Den <b>API Key (v3 auth)</b> kopieren - nicht den "API Read Access Token",
    das ist ein anderes Format fuer v4.</li>
</ol>

<h3>TheTVDB - Alternative fuer Serien</h3>
<p>Spezialisiert auf Serien mit guter Staffel-/Episodenstruktur. Sinnvoll als
Zweitquelle, wenn TMDb eine bestimmte Serie nicht oder nur luecken hat.</p>
<ol>
<li>Konto auf <a href="https://thetvdb.com/auth/register">thetvdb.com</a> anlegen.</li>
<li>Im Dashboard unter <b>API Keys</b> einen Key erzeugen.</li>
<li>Nur bei einem persoenlichen ("Hobbyist"-)Key steht dort zusaetzlich ein
    <b>PIN</b> - den ins PIN-Feld eintragen. Bei einem reinen Projekt-Key ohne
    PIN das Feld einfach leer lassen.</li>
</ol>

<h3>OMDb - ergaenzt IMDb-Rating, springt bei IMDb-IDs ein</h3>
<p>Liefert im normalen Betrieb nur das IMDb-Rating nach, wenn TMDb/TheTVDB es
nicht mitbringen. Zusaetzlich nuetzlich fuer die manuelle Zuordnung per
IMDb-Link: OMDb greift direkt auf IMDbs eigene Daten zu und findet dadurch
manchmal Titel, die TMDb (noch) nicht mit der IMDb-ID verknuepft hat.</p>
<ol>
<li>API-Key anfordern unter <a href="https://www.omdbapi.com/apikey.aspx">omdbapi.com/apikey.aspx</a>
    (kostenlose Stufe reicht, kommt per E-Mail).</li>
<li>Den Key per Bestaetigungslink aus der E-Mail aktivieren.</li>
</ol>

<h3>OpenSubtitles - fuer den Untertitel-Download</h3>
<p>Nur noetig, wenn du fehlende Untertitel automatisch herunterladen willst.
Suchen geht schon mit blossem API-Key, fuer das eigentliche Herunterladen
lohnt sich zusaetzlich ein normaler Account - ohne Login gilt nur ein sehr
kleines Tages-Limit.</p>
<ol>
<li>Account auf <a href="https://www.opensubtitles.com/de/users/sign_up">opensubtitles.com</a> anlegen.</li>
<li>Unter <a href="https://www.opensubtitles.com/de/consumers">opensubtitles.com/consumers</a>
    einen API-Consumer anlegen, dabei einen beliebigen Anwendungsnamen angeben.</li>
<li>API-Key, Benutzername und Passwort in <b>Einstellungen &rarr; Untertitel</b>
    eintragen. Das Passwort wird wie die anderen Keys unverschluesselt lokal
    gespeichert.</li>
</ol>

<h2>Manuell zuordnen per TMDb-/IMDb-Link</h2>
<p>Findet die automatische oder normale Suche einen Titel nicht (z. B. ein
Special, das ungewoehnlich katalogisiert ist), laesst er sich im Dialog
<i>Manuell zuordnen</i> auch direkt per Link oder ID laden:</p>
<ul>
<li>Ein TMDb-Link wie <code>themoviedb.org/movie/12345-...</code> oder
    <code>.../tv/12345-...</code> - die Art (Film/Serie) wird aus der URL erkannt.</li>
<li>Eine blanke TMDb-ID (Zahl).</li>
<li>Ein IMDb-Link oder eine IMDb-ID (<code>tt1234567</code>) - wird zuerst ueber
    TMDb aufgeloest, bei einem Fehlschlag automatisch ueber OMDb.</li>
</ul>

<h2>Scannen</h2>
<p>Erkennt gaengige Szene-Konventionen (<code>S01E05</code>,
<code>1x05</code>, <code>Season 01/E05.mkv</code>) und zusaetzlich:</p>
<ul>
<li><b>Mehrfach-Episoden</b> wie <code>S01E01E02</code> oder
    <code>S01E01-E02</code> - beide Episodennummern werden erkannt statt
    nur der ersten, die Anzeige zeigt <code>S01E01E02</code>.</li>
<li><b>Anime-Nummerierung</b> ohne Staffelangabe (z. B.
    <code>[Gruppe] Serie - 05 [1080p].mkv</code>) - die letzte plausible
    Zahl im Dateinamen wird als durchlaufende Episode uebernommen
    (Staffel 1 angenommen); bekannte Aufloesungswerte (720, 1080, ...)
    werden dabei nicht als Episodennummer missverstanden.</li>
</ul>
<p>Was sich nicht sicher erkennen laesst, landet unauffaellig im
Match-Dialog statt falsch automatisch zugeordnet zu werden.</p>
<p>Rechtsklick auf einen Film oder eine Serie &rarr;
<i>Nur diesen Film/diese Serie scannen</i> liest nur diesen einen Ordner
neu ein, statt jedes Mal die ganze Bibliothek zu durchsuchen. Ein laufender
Scan laesst sich ueber den <i>Abbrechen</i>-Knopf im Fortschrittsdialog
jederzeit unterbrechen, ohne bereits vorhandene Bibliothekseintraege zu
verlieren.</p>

<h2>Umbenennen-Vorlagen</h2>
<p>Unter <b>Einstellungen &rarr; Umbenennen</b> frei einstellbar. Platzhalter:</p>
<ul>
<li>Filme: <code>{title} {year} {ext}</code></li>
<li>Serien: <code>{series} {year} {season} {episode} {episode_end}
    {episode_title} {ext}</code> - <code>{year}</code> ist dabei das Jahr
    der Erstausstrahlung der Serie, <code>{episode_end}</code> nur bei
    Mehrteilern wie <code>S01E01E02</code> belegt (sonst leer).</li>
</ul>
<p>Ein <code>/</code> in der Vorlage legt eine neue Ordnerebene an. Enthaelt ein
Titel selbst ungueltige Zeichen (z. B. einen Schraegstrich bei einer
Doppelfolge), werden die automatisch unschaedlich gemacht - die Vorschau
zeigt das mit einem Hinweis an.</p>

<h2>Sammlungen</h2>
<p>Filme, die TMDb einer Filmreihe zuordnet (z. B. "Alien Collection"), werden
automatisch gruppiert - links im Filme-Tab auswaehlbar. Zusaetzlich lassen
sich per Rechtsklick eigene Sammlungen anlegen, die nie durch einen erneuten
Abgleich ueberschrieben werden. Ist eine TMDb-Sammlung ausgewaehlt, zeigt
moviedesk automatisch an, welche Filme der Reihe noch fehlen (dasselbe gibt
es bei Serien fuer fehlende Episoden) - dafuer ist ein TMDb-Key noetig.</p>

<h2>NFO und Untertitel</h2>
<p><b>NFO erzeugen</b> schreibt Kodi-/Jellyfin-kompatible <code>.nfo</code>-Dateien
neben die Videos (bei Serien zusaetzlich eine <code>tvshow.nfo</code> im
Serienordner) - nur auf Wunsch, nie automatisch. <b>Untertitel herunterladen</b>
sucht fehlende Untertitel in den unter Einstellungen festgelegten Sprachen und
laedt den Treffer mit den meisten Downloads herunter.</p>

<h2>Loeschen</h2>
<p>Verschiebt Dateien in den Papierkorb, nichts wird endgueltig geloescht.
Die Option "ganzes Verzeichnis loeschen" ist deaktiviert, wenn die Datei
direkt im Bibliotheksordner liegt - so laesst sich der Bibliotheksordner
selbst nicht aus Versehen leeren.</p>

<h2>Wo Daten liegen</h2>
<table cellpadding="4">
<tr><td>Einstellungen</td><td><code>~/.config/moviedesk/moviedesk.conf</code></td></tr>
<tr><td>Bibliotheksindex (Zuordnungen)</td><td><code>~/.local/share/moviedesk/library.sqlite</code></td></tr>
<tr><td>Antwort-Cache, Poster</td><td><code>~/.cache/moviedesk/</code></td></tr>
</table>
<p>Der Bibliotheksindex ist die Quelle der Wahrheit fuer Zuordnungen -
Videodateien kennen (anders als Comics mit ComicInfo.xml) kein eingebettetes
Metadatenformat. Beim Umbenennen wird der gespeicherte Pfad automatisch
mitgefuehrt.</p>
"""


class HelpDialog(_HelpDialog):
    def __init__(self, parent=None):
        super().__init__(HELP_HTML, _("Hilfe"), parent)
