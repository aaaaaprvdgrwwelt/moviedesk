"""Bibliotheksindex: SQLite mit einer Zeile je Videodatei.

Anders als bei comicdesk (Wahrheit steht in ComicInfo.xml *in* der Datei)
gibt es fuer Videodateien kein verbreitetes eingebettetes Metadatenformat.
Diese Datenbank ist deshalb die Quelle der Wahrheit fuer Zuordnungen; beim
Umbenennen wird der gespeicherte Pfad von der App selbst nachgezogen.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from deskkit.backup import backup_database

from .providers.base import MediaInfo

MOVIE = "movie"
EPISODE = "episode"

STATUS_MATCHED = "matched"
STATUS_UNSURE = "unsure"
STATUS_UNMATCHED = "unmatched"
STATUS_ERROR = "error"

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    root TEXT NOT NULL,
    title TEXT DEFAULT '',
    year INTEGER,
    season INTEGER,
    episode INTEGER,
    episode_end INTEGER,
    episode_title TEXT DEFAULT '',
    episode_overview TEXT DEFAULT '',
    overview TEXT DEFAULT '',
    genres TEXT DEFAULT '[]',
    rating REAL,
    runtime INTEGER,
    poster_url TEXT,
    poster_path TEXT,
    source TEXT DEFAULT '',
    source_kind TEXT DEFAULT '',
    external_id TEXT DEFAULT '',
    imdb_id TEXT,
    collection TEXT DEFAULT '',
    collection_id TEXT DEFAULT '',
    custom_collection TEXT DEFAULT '',
    score INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'unmatched',
    note TEXT DEFAULT '',
    scanned_at REAL,
    matched_at REAL
)
"""

#: Ausdruck fuer die "wirksame" Sammlung: eine von Hand vergebene Sammlung
#: geht immer vor der von TMDb erkannten - und bleibt beim naechsten
#: automatischen Abgleich unangetastet, weil sie in einer eigenen Spalte steht.
_EFFECTIVE_COLLECTION = "COALESCE(NULLIF(custom_collection, ''), collection)"

#: Spalten, die nach dem ersten Release dazugekommen sind - fuer bereits
#: bestehende Datenbanken per ALTER TABLE nachgezogen (CREATE TABLE IF NOT
#: EXISTS aendert eine vorhandene Tabelle nicht mehr).
_MIGRATIONS = [
    "ALTER TABLE items ADD COLUMN collection TEXT DEFAULT ''",
    "ALTER TABLE items ADD COLUMN custom_collection TEXT DEFAULT ''",
    "ALTER TABLE items ADD COLUMN episode_overview TEXT DEFAULT ''",
    "ALTER TABLE items ADD COLUMN collection_id TEXT DEFAULT ''",
    "ALTER TABLE items ADD COLUMN source_kind TEXT DEFAULT ''",
    "ALTER TABLE items ADD COLUMN episode_end INTEGER",
]


def data_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    path = Path(base) / "moviedesk"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class Item:
    id: int
    kind: str
    path: str
    root: str
    title: str = ""
    year: int | None = None
    season: int | None = None
    episode: int | None = None
    #: Letzte Episode eines Mehrteilers ("S01E01E02" -> episode=1,
    #: episode_end=2), sonst None - siehe parser.ParsedEpisode.
    episode_end: int | None = None
    episode_title: str = ""
    episode_overview: str = ""
    overview: str = ""
    genres: list[str] = field(default_factory=list)
    rating: float | None = None
    runtime: int | None = None
    poster_url: str | None = None
    poster_path: str | None = None
    source: str = ""
    #: "movie"/"series" laut Quelle - unabhaengig von `kind` (Datei-Art).
    #: Meist deckungsgleich, ausser bei einem Special, das die Quelle
    #: ausnahmsweise als Film fuehrt, obwohl die Datei eine Episode ist.
    source_kind: str = ""
    external_id: str = ""
    imdb_id: str | None = None
    collection: str = ""
    collection_id: str = ""
    custom_collection: str = ""
    score: int = 0
    status: str = STATUS_UNMATCHED
    note: str = ""

    @property
    def display_title(self) -> str:
        if self.kind == EPISODE:
            if self.season is not None and self.episode is not None:
                tag = f"S{self.season:02d}E{self.episode:02d}"
                if self.episode_end is not None:
                    tag += f"E{self.episode_end:02d}"
            else:
                tag = ""
            return f"{self.title} {tag}".strip()
        year = f" ({self.year})" if self.year else ""
        return f"{self.title}{year}"

    @property
    def source_url(self) -> str | None:
        """Link zur Seite der Quelle, falls bekannt.

        `source_kind` ist die tatsaechlich getroffene Art laut Quelle
        ("movie"/"series") - unabhaengig von `kind` (Datei-Art). Das
        unterscheidet sich nur bei einem Special, das TMDb ausnahmsweise
        als Film fuehrt, obwohl die Datei eine Episode ist (siehe
        Match-Dialog: dort laesst sich so ein Fall per Direktlink zuordnen).
        Bei aelteren, noch nicht neu zugeordneten Eintraegen ohne
        gespeicherte `source_kind` wird ersatzweise von `kind` ausgegangen."""
        if not self.source or not self.external_id:
            return None
        if self.source == "tmdb":
            is_movie = self.source_kind == "movie" if self.source_kind \
                else self.kind != EPISODE
            path = "movie" if is_movie else "tv"
            return f"https://www.themoviedb.org/{path}/{self.external_id}"
        if self.source == "tvdb":
            return f"https://www.thetvdb.com/dereferrer/series/{self.external_id}"
        if self.source == "omdb":
            return f"https://www.imdb.com/title/{self.imdb_id or self.external_id}/"
        return None


_COLUMNS = [
    "id", "kind", "path", "root", "title", "year", "season", "episode",
    "episode_end",
    "episode_title", "episode_overview", "overview", "genres", "rating",
    "runtime", "poster_url", "poster_path", "source", "source_kind",
    "external_id", "imdb_id", "collection", "collection_id",
    "custom_collection", "score", "status", "note",
]


def _row_to_item(row: sqlite3.Row) -> Item:
    data = dict(row)
    data["genres"] = json.loads(data.get("genres") or "[]")
    return Item(**{k: data.get(k) for k in _COLUMNS})


class LibraryIndex:
    def __init__(self, path: Path | None = None):
        self._path = path or (data_dir() / "library.sqlite")
        self._con = sqlite3.connect(str(self._path), check_same_thread=False)
        self._con.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._con.execute(SCHEMA)
            for migration in _MIGRATIONS:
                try:
                    self._con.execute(migration)
                except sqlite3.OperationalError:
                    pass  # Spalte gibt es schon - Datenbank ist aktuell.
            self._con.commit()

    def close(self) -> None:
        self._con.close()

    def backup_to(self, destination: Path) -> None:
        """Sichert die Datenbank nach `destination` - sicher aufrufbar,
        waehrend die App laeuft (siehe deskkit.backup)."""
        with self._lock:
            backup_database(self._con, destination)

    # --- Scannen --------------------------------------------------------
    def mark_scanned(self, path: Path, kind: str, root: Path,
                     title: str = "", year: int | None = None,
                     season: int | None = None, episode: int | None = None,
                     episode_end: int | None = None) -> None:
        """Datei bekannt machen, falls neu - vorhandene Zuordnung bleibt."""
        with self._lock:
            self._con.execute(
                "INSERT INTO items (kind, path, root, title, year, season, "
                "episode, episode_end, scanned_at) VALUES (?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(path) DO UPDATE SET scanned_at=excluded.scanned_at",
                (kind, str(path), str(root), title, year, season, episode,
                 episode_end, time.time()))
            self._con.commit()

    def forget_missing(self, root: Path, existing: set[str]) -> int:
        """Eintraege loeschen, deren Datei unter `root` nicht mehr da ist."""
        with self._lock:
            rows = self._con.execute(
                "SELECT path FROM items WHERE root=?", (str(root),)).fetchall()
            gone = [r["path"] for r in rows if r["path"] not in existing]
            if gone:
                self._con.executemany(
                    "DELETE FROM items WHERE path=?", [(p,) for p in gone])
                self._con.commit()
            return len(gone)

    def forget_missing_under(self, folder: Path, existing: set[str]) -> int:
        """Wie `forget_missing`, aber nur fuer Eintraege unterhalb `folder` -
        fuer einen gezielten Scan nur einer einzelnen Serie/eines einzelnen
        Films statt des ganzen Wurzelordners."""
        prefix = str(folder).rstrip("/") + "/"
        with self._lock:
            rows = self._con.execute(
                "SELECT path FROM items WHERE path LIKE ? ESCAPE '\\'",
                (prefix.replace("%", "\\%").replace("_", "\\_") + "%",)).fetchall()
            gone = [r["path"] for r in rows if r["path"] not in existing]
            if gone:
                self._con.executemany(
                    "DELETE FROM items WHERE path=?", [(p,) for p in gone])
                self._con.commit()
            return len(gone)

    def remove_path(self, path: Path) -> None:
        """Einzelnen Eintrag entfernen - nachdem seine Datei geloescht wurde."""
        with self._lock:
            self._con.execute("DELETE FROM items WHERE path=?", (str(path),))
            self._con.commit()

    def remove_under(self, folder: Path) -> None:
        """Alle Eintraege unterhalb `folder` entfernen - nach Loeschen des
        ganzen Verzeichnisses."""
        prefix = str(folder).rstrip("/") + "/"
        with self._lock:
            self._con.execute(
                "DELETE FROM items WHERE path LIKE ? ESCAPE '\\'",
                (prefix.replace("%", "\\%").replace("_", "\\_") + "%",))
            self._con.commit()

    # --- Zuordnung --------------------------------------------------------
    def set_match(self, path: Path, info: MediaInfo, score: int, status: str,
                 season: int | None = None, episode: int | None = None,
                 episode_title: str = "", episode_overview: str = "",
                 note: str = "") -> None:
        with self._lock:
            self._con.execute(
                "UPDATE items SET title=?, year=?, overview=?, genres=?, "
                "rating=?, runtime=?, poster_url=?, source=?, source_kind=?, "
                "external_id=?, imdb_id=?, collection=?, collection_id=?, "
                "score=?, status=?, note=?, matched_at=?, "
                "season=COALESCE(?, season), episode=COALESCE(?, episode), "
                "episode_title=?, episode_overview=? WHERE path=?",
                (info.title, info.year, info.overview,
                 json.dumps(info.genres), info.rating, info.runtime,
                 info.poster_url, info.source, info.kind, info.external_id,
                 info.imdb_id, info.collection, info.collection_id, score,
                 status, note, time.time(), season,
                 episode, episode_title, episode_overview, str(path)))
            self._con.commit()

    def reassign_episode(self, path: Path, season: int, episode: int,
                        episode_title: str = "", episode_overview: str = "",
                        note: str = "") -> None:
        """Nur Staffel/Episode (und den passenden Episodentitel) aendern -
        fuer eine von Hand korrigierte Staffelzuordnung bei einer Serie, die
        schon bekannt ist. Die Serie selbst wird nicht neu zugeordnet."""
        with self._lock:
            self._con.execute(
                "UPDATE items SET season=?, episode=?, episode_title=?, "
                "episode_overview=?, note=?, matched_at=? WHERE path=?",
                (season, episode, episode_title, episode_overview, note,
                 time.time(), str(path)))
            self._con.commit()

    def set_status(self, path: Path, status: str, note: str = "") -> None:
        with self._lock:
            self._con.execute(
                "UPDATE items SET status=?, note=? WHERE path=?",
                (status, note, str(path)))
            self._con.commit()

    def set_poster_path(self, path: Path, poster_path: str) -> None:
        with self._lock:
            self._con.execute(
                "UPDATE items SET poster_path=? WHERE path=?",
                (poster_path, str(path)))
            self._con.commit()

    def update_path(self, old: Path, new: Path) -> None:
        with self._lock:
            self._con.execute(
                "UPDATE items SET path=? WHERE path=?", (str(new), str(old)))
            self._con.commit()

    # --- Lesen --------------------------------------------------------
    def get(self, path: Path) -> Item | None:
        with self._lock:
            row = self._con.execute(
                "SELECT * FROM items WHERE path=?", (str(path),)).fetchone()
        return _row_to_item(row) if row else None

    def list_movies(self, collection: str | None = None) -> list[Item]:
        with self._lock:
            if collection is None:
                rows = self._con.execute(
                    "SELECT * FROM items WHERE kind='movie' "
                    "ORDER BY title COLLATE NOCASE, year").fetchall()
            else:
                rows = self._con.execute(
                    f"SELECT * FROM items WHERE kind='movie' "
                    f"AND {_EFFECTIVE_COLLECTION}=? "
                    "ORDER BY year, title COLLATE NOCASE", (collection,)).fetchall()
        return [_row_to_item(r) for r in rows]

    def collections(self) -> list[tuple[str, int]]:
        """Bekannte Filmreihen mit Anzahl - eigene ueberschreiben die von TMDb
        erkannten (siehe `_EFFECTIVE_COLLECTION`), alphabetisch sortiert."""
        with self._lock:
            rows = self._con.execute(
                f"SELECT {_EFFECTIVE_COLLECTION} AS name, COUNT(*) AS n FROM items "
                f"WHERE kind='movie' AND {_EFFECTIVE_COLLECTION} != '' "
                "GROUP BY name ORDER BY name COLLATE NOCASE").fetchall()
        return [(r["name"], r["n"]) for r in rows]

    def custom_collection_names(self) -> list[str]:
        with self._lock:
            rows = self._con.execute(
                "SELECT DISTINCT custom_collection FROM items "
                "WHERE custom_collection != '' "
                "ORDER BY custom_collection COLLATE NOCASE").fetchall()
        return [r["custom_collection"] for r in rows]

    def set_custom_collection(self, path: Path, name: str) -> None:
        """Eigene Sammlung setzen oder (mit leerem `name`) wieder entfernen -
        eine entfernte Zuordnung faellt zurueck auf die von TMDb erkannte."""
        with self._lock:
            self._con.execute(
                "UPDATE items SET custom_collection=? WHERE path=?",
                (name.strip(), str(path)))
            self._con.commit()

    def list_episodes(self) -> list[Item]:
        with self._lock:
            rows = self._con.execute(
                "SELECT * FROM items WHERE kind='episode' "
                "ORDER BY title COLLATE NOCASE, season, episode").fetchall()
        return [_row_to_item(r) for r in rows]

    def series_groups(self) -> list[tuple[str, list[Item]]]:
        """Episoden nach Serientitel gruppiert (Gross-/Kleinschreibung egal -
        sonst wuerden z. B. "futurama" und "Futurama" aus unterschiedlich
        benannten Dateien als zwei getrennte Serien auftauchen), Titel
        alphabetisch. Als Anzeigename gewinnt der Titel eines bereits
        zugeordneten Eintrags (korrekte Schreibweise laut Quelle), sonst der
        zuerst gefundene rohe Dateiname-Titel."""
        by_key: dict[str, list[Item]] = {}
        for item in self.list_episodes():
            key = (item.title or "?").casefold()
            by_key.setdefault(key, []).append(item)
        groups = [
            (next((i.title for i in items if i.source), None)
             or items[0].title or "?", items)
            for items in by_key.values()
        ]
        return sorted(groups, key=lambda kv: kv[0].casefold())

    def unresolved(self) -> list[Item]:
        with self._lock:
            rows = self._con.execute(
                "SELECT * FROM items WHERE status IN (?, ?) "
                "ORDER BY path", (STATUS_UNSURE, STATUS_UNMATCHED)).fetchall()
        return [_row_to_item(r) for r in rows]

    def all_items(self) -> list[Item]:
        with self._lock:
            rows = self._con.execute("SELECT * FROM items ORDER BY path").fetchall()
        return [_row_to_item(r) for r in rows]
