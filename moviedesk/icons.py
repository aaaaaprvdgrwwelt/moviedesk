"""Eigene Icons als SVG.

Icon-Themes gibt es unter Windows und macOS nicht und unter Linux nicht
zuverlaessig. Deshalb werden die paar gebrauchten Symbole selbst gezeichnet.
Sie uebernehmen die Textfarbe der Palette und funktionieren damit in hellen
wie dunklen Themes.
"""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

#: Strichzeichnungen auf einem 24x24-Raster.
PATHS = {
    "refresh": '<path d="M20 12a8 8 0 1 1-2.3-5.6"/><path d="M20 4v4h-4"/>',
    "help": '<circle cx="12" cy="12" r="9"/>'
            '<path d="M9.3 9.3a2.7 2.7 0 1 1 3.8 2.5c-.8.4-1.1 1-1.1 1.9"/>'
            '<circle cx="12" cy="17" r="0.1" stroke-width="2.4"/>',
    "play": '<circle cx="12" cy="12" r="9"/><path d="M10 8.5l6 3.5-6 3.5z"/>',
    "rename": '<path d="M4 20h5l9.5-9.5a2.1 2.1 0 0 0-3-3L6 17z"/><path d="M14.5 6.5l3 3"/>',
    "match": '<path d="M11 3H4a1 1 0 0 0-1 1v7l9.5 9.5a1.5 1.5 0 0 0 2.1 0l6-6a1.5 1.5 0 0 0 0-2.1z"/>'
             '<circle cx="7.5" cy="7.5" r="1.4"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5 5"/>',
    "folder_new": '<path d="M3 7a1 1 0 0 1 1-1h5l2 2h8a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/>'
                  '<path d="M12 11v5M9.5 13.5h5"/>',
    "folder": '<path d="M3 7a1 1 0 0 1 1-1h5l2 2h8a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/>',
    "delete": '<path d="M4 7h16"/><path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>'
              '<path d="M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12"/>'
              '<path d="M10 11v6M14 11v6"/>',
    "nfo": '<path d="M7 3h7l4 4v14H7z"/><path d="M14 3v4h4"/>'
           '<path d="M9.5 12.5h5M9.5 15.5h5M9.5 18h3"/>',
    "subtitle": '<rect x="3" y="6" width="18" height="12" rx="2"/>'
                '<path d="M7 12h2M11 12h6M7 15.5h4M13 15.5h4"/>',
    "settings": '<circle cx="12" cy="12" r="3"/>'
                '<path d="M12 2.5v3M12 18.5v3M21.5 12h-3M5.5 12h-3'
                'M18.7 5.3l-2.1 2.1M7.4 16.6l-2.1 2.1M18.7 18.7l-2.1-2.1M7.4 7.4L5.3 5.3"/>',
    "movie": '<rect x="3" y="6" width="18" height="13" rx="1.5"/>'
             '<path d="M3 6l3-3h3l-3 3M10 6l3-3h3l-3 3M17 6l2-2"/>',
    "tv": '<rect x="3" y="5" width="18" height="12" rx="1.5"/><path d="M8 20h8M12 17v3"/>',
    "star": '<path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z"/>',
    "check": '<path d="M4 12.5l5 5L20 6"/>',
    "warn": '<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17.2v.1"/>',
    "left": '<path d="M19 12H6M12 6l-6 6 6 6"/>',
    "right": '<path d="M5 12h13M12 6l6 6-6 6"/>',
}

_TEMPLATE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="{color}" stroke-width="1.7" stroke-linecap="round" '
    'stroke-linejoin="round">{body}</svg>'
)

_cache: dict[tuple[str, str, int], QIcon] = {}


def _text_color() -> QColor:
    app = QApplication.instance()
    if app is None:
        return QColor("#303030")
    return app.palette().color(QPalette.WindowText)


def icon(name: str, size: int = 24, color: str | None = None) -> QIcon:
    """Icon `name` in Textfarbe. Unbekannte Namen ergeben ein leeres Icon."""
    body = PATHS.get(name)
    if not body:
        return QIcon()
    color = QColor(color) if color else _text_color()
    key = (name, color.name(), size)
    if key in _cache:
        return _cache[key]

    svg = _TEMPLATE.format(color=color.name(), body=body)
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    result = QIcon()
    for scale in (1, 2):
        pixmap = QPixmap(size * scale, size * scale)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter, QRectF(pixmap.rect()))
        painter.end()
        pixmap.setDevicePixelRatio(scale)
        result.addPixmap(pixmap)
    _cache[key] = result
    return result
