from pathlib import Path

from moviedesk.library import LibraryIndex, MOVIE
from moviedesk.scanner import ScanWorker, scan_folder


def make_movies(root: Path, count: int) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        (root / f"Movie {i} (2020).mkv").write_bytes(b"")


def test_scan_worker_stop_halts_processing_mid_scan(tmp_path):
    root = tmp_path / "movies"
    make_movies(root, 20)
    library = LibraryIndex(tmp_path / "library.sqlite")
    worker = ScanWorker([str(root)], [], library)

    original = library.mark_scanned
    calls = []

    def counting(*args, **kwargs):
        calls.append(1)
        if len(calls) == 5:
            worker.stop()
        return original(*args, **kwargs)

    library.mark_scanned = counting
    worker.run()

    assert len(calls) == 5
    assert len(library.all_items()) == 5


def test_scan_worker_without_stop_processes_everything(tmp_path):
    root = tmp_path / "movies"
    make_movies(root, 7)
    library = LibraryIndex(tmp_path / "library.sqlite")
    worker = ScanWorker([str(root)], [], library)
    worker.run()
    assert len(library.all_items()) == 7


def test_scan_worker_stop_does_not_wrongly_forget_existing_entries(tmp_path):
    # forget_missing() nach einem Abbruch darf nur tatsaechlich fehlende
    # Dateien loeschen - der find_videos()-Durchlauf selbst ist immer
    # vollstaendig, nur die anschliessende Verarbeitung wird abgebrochen.
    root = tmp_path / "movies"
    make_movies(root, 10)
    library = LibraryIndex(tmp_path / "library.sqlite")
    ScanWorker([str(root)], [], library).run()
    assert len(library.all_items()) == 10

    worker = ScanWorker([str(root)], [], library)
    calls = []
    original = library.mark_scanned

    def counting(*args, **kwargs):
        calls.append(1)
        if len(calls) == 3:
            worker.stop()
        return original(*args, **kwargs)

    library.mark_scanned = counting
    worker.run()
    # Trotz Abbruch bleiben alle zehn vorhandenen Dateien in der Bibliothek -
    # forget_missing() haette sie sonst faelschlich als fehlend geloescht.
    assert len(library.all_items()) == 10


def test_scan_folder_should_stop_halts_processing(tmp_path):
    root = tmp_path / "movies"
    make_movies(root, 10)
    library = LibraryIndex(tmp_path / "library.sqlite")
    calls = []

    def should_stop():
        calls.append(1)
        return len(calls) > 3

    scan_folder(root, root, MOVIE, library, should_stop=should_stop)
    assert len(library.all_items()) == 3
