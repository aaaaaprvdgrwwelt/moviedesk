"""Einstellungen, gehalten in QSettings."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from PySide6.QtCore import QSettings

from deskkit.secrets import get_secret, set_secret
from deskkit.settings import as_bool as _bool

from .i18n import system_language
from .matcher import DEFAULT_THRESHOLD, MatchConfig
from .providers.base import MetadataProvider
from .providers.omdb import OMDbProvider
from .providers.tmdb import TMDbProvider
from .providers.tvdb import TVDBProvider
from .subtitles import DEFAULT_LANGUAGES, OpenSubtitlesClient

#: TMDb erwartet "de-DE"/"en-US" statt der einfachen Sprachcodes der Oberflaeche.
_TMDB_LANGUAGE = {"de": "de-DE", "en": "en-US"}

MOVIE_TEMPLATE_DEFAULT = "{title} ({year})/{title} ({year}){ext}"
SERIES_TEMPLATE_DEFAULT = (
    "{series} ({year})/Season {season:02d}/"
    "{series} - S{season:02d}E{episode:02d} - {episode_title}{ext}"
)


@dataclass
class Settings:
    tmdb_key: str = ""
    use_tmdb: bool = True
    omdb_key: str = ""
    use_omdb: bool = False
    tvdb_key: str = ""
    tvdb_pin: str = ""
    use_tvdb: bool = False
    threshold: int = DEFAULT_THRESHOLD
    movie_template: str = MOVIE_TEMPLATE_DEFAULT
    series_template: str = SERIES_TEMPLATE_DEFAULT
    movie_roots: list[str] = field(default_factory=list)
    series_roots: list[str] = field(default_factory=list)
    language: str = "auto"
    opensubtitles_key: str = ""
    opensubtitles_user: str = ""
    opensubtitles_pass: str = ""
    use_subtitles: bool = False
    subtitle_languages: str = DEFAULT_LANGUAGES
    #: "poster.jpg" zusaetzlich lokal neben Film/Serie ablegen (fuer
    #: Kodi/Jellyfin/Plex ohne Internetzugriff) - nur beim "NFO erzeugen".
    save_local_posters: bool = False
    #: Bei "Fehlende Teile" (Filme/Episoden) nur anzeigen, was laut TMDb
    #: bereits veroeffentlicht/ausgestrahlt wurde - nicht laenderspezifisch
    #: bei Episoden, TMDb kennt dort nur ein weltweites Datum.
    only_released_missing: bool = False
    #: ISO-3166-1-Ländercode fuer das Veroeffentlichungsdatum bei Filmen.
    release_country: str = "DE"

    @classmethod
    def load(cls, settings: QSettings) -> "Settings":
        settings.beginGroup("moviedesk")
        obj = cls(
            tmdb_key=get_secret(settings, "moviedesk", "tmdb_key"),
            use_tmdb=_bool(settings.value("use_tmdb"), True),
            omdb_key=get_secret(settings, "moviedesk", "omdb_key"),
            use_omdb=_bool(settings.value("use_omdb"), False),
            tvdb_key=get_secret(settings, "moviedesk", "tvdb_key"),
            tvdb_pin=get_secret(settings, "moviedesk", "tvdb_pin"),
            use_tvdb=_bool(settings.value("use_tvdb"), False),
            threshold=int(settings.value("threshold", DEFAULT_THRESHOLD)),
            movie_template=settings.value("movie_template", MOVIE_TEMPLATE_DEFAULT)
            or MOVIE_TEMPLATE_DEFAULT,
            series_template=settings.value(
                "series_template", SERIES_TEMPLATE_DEFAULT) or SERIES_TEMPLATE_DEFAULT,
            movie_roots=json.loads(settings.value("movie_roots", "[]") or "[]"),
            series_roots=json.loads(settings.value("series_roots", "[]") or "[]"),
            language=settings.value("language", "auto") or "auto",
            opensubtitles_key=get_secret(settings, "moviedesk", "opensubtitles_key"),
            opensubtitles_user=settings.value("opensubtitles_user", "") or "",
            opensubtitles_pass=get_secret(settings, "moviedesk", "opensubtitles_pass"),
            use_subtitles=_bool(settings.value("use_subtitles"), False),
            subtitle_languages=settings.value(
                "subtitle_languages", DEFAULT_LANGUAGES) or DEFAULT_LANGUAGES,
            save_local_posters=_bool(settings.value("save_local_posters"), False),
            only_released_missing=_bool(settings.value("only_released_missing"), False),
            release_country=settings.value("release_country", "DE") or "DE",
        )
        settings.endGroup()
        return obj

    #: Diese Felder landen im System-Schluesselbund statt im Klartext in
    #: QSettings (siehe deskkit.secrets) - opensubtitles_user bleibt aussen
    #: vor, das ist nur ein Anmeldename, kein Geheimnis.
    _SECRET_FIELDS = (
        "tmdb_key", "omdb_key", "tvdb_key", "tvdb_pin",
        "opensubtitles_key", "opensubtitles_pass",
    )

    def save(self, settings: QSettings) -> None:
        settings.beginGroup("moviedesk")
        for key, value in self.__dict__.items():
            if key in self._SECRET_FIELDS:
                set_secret(settings, "moviedesk", key, value)
                continue
            if isinstance(value, list):
                value = json.dumps(value)
            settings.setValue(key, value)
        settings.endGroup()
        settings.sync()

    # ------------------------------------------------------------------
    def tmdb_language(self) -> str:
        code = system_language() if self.language == "auto" else self.language
        return _TMDB_LANGUAGE.get(code, "en-US")

    def build_providers(self) -> list[MetadataProvider]:
        providers: list[MetadataProvider] = []
        if self.use_tmdb and self.tmdb_key.strip():
            providers.append(TMDbProvider(self.tmdb_key, self.tmdb_language()))
        if self.use_tvdb and self.tvdb_key.strip():
            providers.append(TVDBProvider(self.tvdb_key, self.tvdb_pin))
        if self.use_omdb and self.omdb_key.strip():
            providers.append(OMDbProvider(self.omdb_key))
        return providers

    def build_config(self) -> MatchConfig:
        return MatchConfig(threshold=self.threshold, providers=self.build_providers())

    def subtitle_language_list(self) -> list[str]:
        return [c.strip() for c in self.subtitle_languages.split(",") if c.strip()]

    def build_subtitle_client(self) -> OpenSubtitlesClient | None:
        if not (self.use_subtitles and self.opensubtitles_key.strip()):
            return None
        return OpenSubtitlesClient(
            self.opensubtitles_key, self.opensubtitles_user, self.opensubtitles_pass)
