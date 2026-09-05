from pathlib import Path

from moviedesk.parser import is_sample_or_extra, parse_episode, parse_movie


def test_parse_movie_title_and_year_from_filename():
    parsed = parse_movie(Path("/movies/Inception (2010) 1080p BluRay x264.mkv"))
    assert parsed.title == "Inception"
    assert parsed.year == 2010


def test_parse_movie_falls_back_to_folder_year_when_filename_is_generic():
    parsed = parse_movie(Path("/movies/The Matrix (1999)/movie.mkv"))
    assert parsed.title == "The Matrix"
    assert parsed.year == 1999


def test_parse_movie_no_year_strips_release_noise():
    parsed = parse_movie(Path("/movies/Some.Documentary.WEBRip.x264.mkv"))
    assert parsed.title == "Some Documentary"
    assert parsed.year is None


def test_parse_episode_sxxeyy_pattern():
    parsed = parse_episode(
        Path("/series/Breaking Bad/Season 1/Breaking.Bad.S01E05.720p.mkv"))
    assert parsed.series == "Breaking Bad"
    assert parsed.season == 1
    assert parsed.episode == 5


def test_parse_episode_nxnn_pattern():
    parsed = parse_episode(Path("/series/Futurama/Futurama.1x03.avi"))
    assert parsed.series == "Futurama"
    assert parsed.season == 1
    assert parsed.episode == 3


def test_parse_episode_season_folder_with_bare_episode_number():
    parsed = parse_episode(Path("/series/Futurama/Season 11/E05.mkv"))
    assert parsed.series == "Futurama"
    assert parsed.season == 11
    assert parsed.episode == 5


def test_parse_episode_no_pattern_returns_none():
    assert parse_episode(Path("/series/random-file.mkv")) is None


def test_parse_episode_extra_large_is_not_mistaken_for_noise():
    # Regressionstest: "Extra Large Medium" wurde faelschlich als
    # Sample/Bonusmaterial erkannt und der Titel dadurch abgeschnitten.
    parsed = parse_episode(
        Path("/series/Family Guy (1999)/Season 8/"
             "Family Guy - S08E12 - Extra Large Medium SDTV.avi"))
    assert parsed.series == "Family Guy"
    assert parsed.season == 8
    assert parsed.episode == 12
    assert "Extra Large Medium" in parsed.guessed_title


def test_parse_episode_multi_episode_concatenated():
    parsed = parse_episode(Path("/series/Show/Show.S01E01E02.mkv"))
    assert parsed.season == 1
    assert parsed.episode == 1
    assert parsed.episode_end == 2


def test_parse_episode_multi_episode_with_dash_and_e():
    # clean_words() macht den Bindestrich vor dem Titel zu Leerzeichen -
    # "S01E01-E02 - Titel" kommt hier als "S01E01 E02  Titel" an.
    parsed = parse_episode(
        Path("/series/Show/Show - S01E01-E02 - Double Episode.mkv"))
    assert parsed.season == 1
    assert parsed.episode == 1
    assert parsed.episode_end == 2
    assert "Double Episode" in parsed.guessed_title


def test_parse_episode_multi_episode_bare_second_number():
    parsed = parse_episode(Path("/series/Show/Show - S01E01-02.mkv"))
    assert parsed.season == 1
    assert parsed.episode == 1
    assert parsed.episode_end == 2


def test_parse_episode_single_episode_has_no_episode_end():
    parsed = parse_episode(Path("/series/Show/Show.S01E05.mkv"))
    assert parsed.episode_end is None


def test_parse_episode_anime_absolute_numbering_assumes_season_one():
    parsed = parse_episode(
        Path("/series/Anime/[SubGroup] Anime Name - 05 [1080p][ABCD1234].mkv"))
    assert parsed.series == "Anime Name"
    assert parsed.season == 1
    assert parsed.episode == 5


def test_parse_episode_anime_absolute_numbering_zero_padded():
    parsed = parse_episode(Path("/series/Anime/Anime Name - 005.mkv"))
    assert parsed.series == "Anime Name"
    assert parsed.season == 1
    assert parsed.episode == 5


def test_parse_episode_anime_fallback_ignores_bare_resolution_numbers():
    # "720"/"1080" etc. sind keine Episodennummern, auch wenn sie als
    # blanke Zahl im Dateinamen stehen.
    assert parse_episode(Path("/series/Anime/Anime Name 1080.mkv")) is None


def test_is_sample_or_extra_true_for_bonus_material():
    assert is_sample_or_extra("Movie.Title.2020.Sample.mkv") is True
    assert is_sample_or_extra("Show.S01.Trailer.mkv") is True


def test_is_sample_or_extra_false_when_episode_marker_present():
    # Ein SxxEyy/NxNN-Treffer macht "extra" zum Episodentitel, nicht zu Bonusmaterial.
    assert is_sample_or_extra(
        "Family Guy - S08E12 - Extra Large Medium SDTV.avi") is False


def test_is_sample_or_extra_false_for_normal_filename():
    assert is_sample_or_extra("Inception.2010.1080p.BluRay.mkv") is False
