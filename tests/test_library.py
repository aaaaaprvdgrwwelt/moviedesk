from pathlib import Path

from moviedesk.library import EPISODE, STATUS_MATCHED, LibraryIndex
from moviedesk.providers.base import MediaInfo


def make_index(tmp_path) -> LibraryIndex:
    return LibraryIndex(tmp_path / "library.sqlite")


def test_mark_scanned_inserts_new_item(tmp_path):
    index = make_index(tmp_path)
    index.mark_scanned(Path("/series/Show/S01E01.mkv"), EPISODE,
                       Path("/series"), title="Show", season=1, episode=1)
    items = index.list_episodes()
    assert len(items) == 1
    assert items[0].title == "Show"
    assert items[0].season == 1
    assert items[0].episode == 1


def test_mark_scanned_keeps_existing_match_on_rescan(tmp_path):
    index = make_index(tmp_path)
    path = Path("/series/Show/S01E01.mkv")
    index.mark_scanned(path, EPISODE, Path("/series"), title="Show")
    info = MediaInfo(kind="series", title="Show (matched)", source="tmdb",
                     external_id="123")
    index.set_match(path, info, score=95, status=STATUS_MATCHED,
                    season=1, episode=1, episode_title="Pilot")
    # Erneutes Scannen darf eine bereits gesetzte Zuordnung nicht ueberschreiben.
    index.mark_scanned(path, EPISODE, Path("/series"), title="Show")
    items = index.list_episodes()
    assert len(items) == 1
    assert items[0].title == "Show (matched)"
    assert items[0].status == STATUS_MATCHED


def test_forget_missing_removes_gone_files(tmp_path):
    index = make_index(tmp_path)
    root = Path("/series")
    index.mark_scanned(root / "Show" / "S01E01.mkv", EPISODE, root, title="Show")
    index.mark_scanned(root / "Show" / "S01E02.mkv", EPISODE, root, title="Show")
    removed = index.forget_missing(root, {str(root / "Show" / "S01E01.mkv")})
    assert removed == 1
    remaining = [i.path for i in index.list_episodes()]
    assert remaining == [str(root / "Show" / "S01E01.mkv")]


def test_forget_missing_under_only_touches_given_folder(tmp_path):
    index = make_index(tmp_path)
    root = Path("/series")
    index.mark_scanned(root / "ShowA" / "S01E01.mkv", EPISODE, root, title="ShowA")
    index.mark_scanned(root / "ShowB" / "S01E01.mkv", EPISODE, root, title="ShowB")
    removed = index.forget_missing_under(root / "ShowA", set())
    assert removed == 1
    remaining_titles = {i.title for i in index.list_episodes()}
    assert remaining_titles == {"ShowB"}


def test_series_groups_are_case_insensitive(tmp_path):
    # Regressionstest: "futurama" und "Futurama" duerfen keine zwei
    # getrennten Serien ergeben.
    index = make_index(tmp_path)
    root = Path("/series")
    index.mark_scanned(root / "futurama" / "S11E01.mkv", EPISODE, root,
                       title="futurama", season=11, episode=1)
    index.mark_scanned(root / "Futurama" / "S11E02.mkv", EPISODE, root,
                       title="Futurama", season=11, episode=2)
    groups = index.series_groups()
    assert len(groups) == 1
    name, items = groups[0]
    assert len(items) == 2


def test_series_groups_prefers_matched_title_as_display_name(tmp_path):
    index = make_index(tmp_path)
    root = Path("/series")
    path1 = root / "futurama" / "S11E01.mkv"
    path2 = root / "Futurama" / "S11E02.mkv"
    index.mark_scanned(path1, EPISODE, root, title="futurama", season=11, episode=1)
    index.mark_scanned(path2, EPISODE, root, title="Futurama", season=11, episode=2)
    info = MediaInfo(kind="series", title="Futurama", year=1999,
                     source="tmdb", external_id="615")
    index.set_match(path2, info, score=95, status=STATUS_MATCHED,
                    season=11, episode=2)
    groups = index.series_groups()
    assert groups[0][0] == "Futurama"
