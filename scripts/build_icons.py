from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication, QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "src" / "mpn_tolkning" / "assets"
SIZES = (16, 24, 32, 48, 64, 128, 256)


def render_png(svg_path: Path, size: int, output: Path) -> None:
    renderer = QSvgRenderer(str(svg_path))
    if not renderer.isValid():
        raise ValueError(f"Invalid SVG: {svg_path}")
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    if not image.save(str(output), "PNG"):
        raise OSError(f"Could not write {output}")


def main() -> None:
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    ASSETS.mkdir(parents=True, exist_ok=True)
    svg = ASSETS / "variant-lens.svg"
    rendered = []
    for size in SIZES:
        target = ASSETS / f"variant-lens-{size}.png"
        render_png(svg, size, target)
        rendered.append(target)
    (ASSETS / "variant-lens.png").write_bytes((ASSETS / "variant-lens-256.png").read_bytes())
    images = [Image.open(path).convert("RGBA") for path in rendered]
    largest = images[-1]
    largest.save(
        ASSETS / "variant-lens.ico",
        format="ICO",
        append_images=images[:-1],
        sizes=[(size, size) for size in SIZES],
        bitmap_format="png",
    )
    for image in images:
        image.close()
    del app


if __name__ == "__main__":
    main()
