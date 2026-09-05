from unittest.mock import patch

from PySide6.QtCore import QSettings

from moviedesk.config import Settings


def make_settings(tmp_path) -> QSettings:
    return QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)


def test_save_and_load_roundtrip_without_keyring(tmp_path):
    # Ohne Schluesselbund (z. B. hier im Test) landen Geheimnisse weiterhin
    # in QSettings - Rueckfallverhalten, kein Datenverlust.
    with patch("deskkit.secrets.available", return_value=False):
        settings = make_settings(tmp_path)
        cfg = Settings(tmdb_key="abc123", omdb_key="def456", movie_roots=["/movies"])
        cfg.save(settings)

        settings2 = make_settings(tmp_path)
        loaded = Settings.load(settings2)
    assert loaded.tmdb_key == "abc123"
    assert loaded.omdb_key == "def456"
    assert loaded.movie_roots == ["/movies"]


def test_save_does_not_store_secrets_in_plaintext_when_keyring_available(tmp_path):
    with patch("deskkit.secrets.available", return_value=True), \
         patch("deskkit.secrets.keyring") as mock_keyring:
        settings = make_settings(tmp_path)
        cfg = Settings(tmdb_key="abc123")
        cfg.save(settings)

    settings.beginGroup("moviedesk")
    stored_plaintext = settings.value("tmdb_key")
    settings.endGroup()
    assert stored_plaintext is None
    mock_keyring.set_password.assert_any_call("moviedesk", "tmdb_key", "abc123")


def test_load_migrates_legacy_plaintext_key_into_keyring(tmp_path):
    # Vor dieser Umstellung gespeicherte Klartext-Werte sollen beim naechsten
    # Laden automatisch in den Schluesselbund wandern, nicht verloren gehen.
    settings = make_settings(tmp_path)
    settings.beginGroup("moviedesk")
    settings.setValue("tmdb_key", "legacy-key")
    settings.endGroup()

    with patch("deskkit.secrets.available", return_value=True), \
         patch("deskkit.secrets.keyring") as mock_keyring:
        mock_keyring.get_password.return_value = None
        loaded = Settings.load(settings)

    assert loaded.tmdb_key == "legacy-key"
    mock_keyring.set_password.assert_any_call("moviedesk", "tmdb_key", "legacy-key")
