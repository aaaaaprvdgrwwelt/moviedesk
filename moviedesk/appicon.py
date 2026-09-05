"""Programmsymbol."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon

ASSETS = Path(__file__).parent / "assets"
SVG = ASSETS / "moviedesk.svg"

SIZES = (16, 22, 24, 32, 48, 64, 128, 256, 512)

_cached: QIcon | None = None


def icon() -> QIcon:
    global _cached
    if _cached is not None:
        return _cached
    base = QIcon(str(SVG))
    result = QIcon()
    for size in SIZES:
        result.addPixmap(base.pixmap(size, size))
    _cached = result
    return result


def _index_theme(sizes: tuple[int, ...]) -> str:
    folders = [f"{size}x{size}/apps" for size in sizes] + ["scalable/apps"]
    lines = ["[Icon Theme]", "Name=Hicolor", "Comment=Fallback icon theme",
             "Hidden=true", "Directories=" + ",".join(folders), ""]
    for size in sizes:
        lines += [f"[{size}x{size}/apps]", f"Size={size}",
                  "Context=Applications", "Type=Fixed", ""]
    lines += ["[scalable/apps]", "Size=48", "MinSize=8", "MaxSize=512",
              "Context=Applications", "Type=Scalable", ""]
    return "\n".join(lines)


def install(target: Path | None = None) -> list[Path]:
    """PNGs ins Icon-Thema legen, damit Menue und Fensterleiste sie finden."""
    base_dir = target or (Path.home() / ".local" / "share" / "icons" / "hicolor")
    written: list[Path] = []
    base = QIcon(str(SVG))
    for size in SIZES:
        folder = base_dir / f"{size}x{size}" / "apps"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "moviedesk.png"
        base.pixmap(size, size).save(str(path), "PNG")
        written.append(path)
    scalable = base_dir / "scalable" / "apps"
    scalable.mkdir(parents=True, exist_ok=True)
    target_svg = scalable / "moviedesk.svg"
    target_svg.write_bytes(SVG.read_bytes())
    written.append(target_svg)

    index = base_dir / "index.theme"
    index.write_text(_index_theme(SIZES), "utf-8")
    written.append(index)
    return written


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    QApplication(sys.argv)
    for path in install():
        print(path)
