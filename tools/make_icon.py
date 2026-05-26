"""Generate the application icon (a maritime compass rose on parchment).

Produces, under branding/:
    app.png   1024x1024 master
    app.icns  macOS icon (built via the system iconutil)
    app.ico   Windows icon

Run:
    .venv/bin/python tools/make_icon.py

The generated files are committed to the repo; the release workflow does not
regenerate them, it just feeds them to PyInstaller (build.spec).
"""
from __future__ import annotations
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6 import QtCore, QtGui

ROOT = Path(__file__).resolve().parents[1]
BRANDING = ROOT / "branding"
SIZE = 1024

# Palette (old-map aesthetic)
PARCHMENT_TOP = QtGui.QColor(0xEA, 0xDA, 0xB4)
PARCHMENT_BOT = QtGui.QColor(0xD2, 0xB9, 0x8A)
NAVY = QtGui.QColor(0x1C, 0x3A, 0x4F)
NAVY_LIGHT = QtGui.QColor(0x2E, 0x5A, 0x78)
DARK_RED = QtGui.QColor(0x8A, 0x2A, 0x22)
RED_LIGHT = QtGui.QColor(0xB1, 0x3A, 0x30)
GOLD = QtGui.QColor(0xC9, 0x9A, 0x3A)


def _point(cx: float, cy: float, angle_deg: float, dist: float) -> QtCore.QPointF:
    a = math.radians(angle_deg)
    return QtCore.QPointF(cx + dist * math.sin(a), cy - dist * math.cos(a))


def _draw_compass(p: QtGui.QPainter, cx: float, cy: float) -> None:
    long_len = SIZE * 0.40
    short_len = SIZE * 0.26
    base = SIZE * 0.052

    def draw_star(length: float, dark: QtGui.QColor, light: QtGui.QColor, offset: float):
        for k in range(4):
            ang = offset + k * 90
            tip = _point(cx, cy, ang, length)
            bl = _point(cx, cy, ang - 90, base)
            br = _point(cx, cy, ang + 90, base)
            # right half (darker), left half (lighter) for a beveled look
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(dark)
            p.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(cx, cy), tip, br]))
            p.setBrush(light)
            p.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(cx, cy), tip, bl]))

    # Diagonal (short) points first, then cardinal (long) on top.
    draw_star(short_len, DARK_RED, RED_LIGHT, offset=45)
    draw_star(long_len, NAVY, NAVY_LIGHT, offset=0)

    # Centre hub
    hub_r = SIZE * 0.045
    p.setBrush(GOLD)
    p.setPen(QtGui.QPen(NAVY, SIZE * 0.006))
    p.drawEllipse(QtCore.QPointF(cx, cy), hub_r, hub_r)


def render_master() -> QtGui.QImage:
    img = QtGui.QImage(SIZE, SIZE, QtGui.QImage.Format_ARGB32)
    img.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(img)
    try:
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        margin = SIZE * 0.08
        rect = QtCore.QRectF(margin, margin, SIZE - 2 * margin, SIZE - 2 * margin)
        radius = (SIZE - 2 * margin) * 0.22

        # Parchment tile with a subtle vertical gradient
        grad = QtGui.QLinearGradient(0, rect.top(), 0, rect.bottom())
        grad.setColorAt(0.0, PARCHMENT_TOP)
        grad.setColorAt(1.0, PARCHMENT_BOT)
        path = QtGui.QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        p.fillPath(path, QtGui.QBrush(grad))

        # Navy ring just inside the tile edge
        ring = QtGui.QPainterPath()
        inset = SIZE * 0.018
        ring_rect = rect.adjusted(inset, inset, -inset, -inset)
        ring.addRoundedRect(ring_rect, radius * 0.9, radius * 0.9)
        p.setBrush(QtCore.Qt.NoBrush)
        p.setPen(QtGui.QPen(NAVY, SIZE * 0.012))
        p.drawPath(ring)

        _draw_compass(p, SIZE / 2, SIZE / 2)
    finally:
        p.end()
    return img


def make_icns(master_png: Path) -> None:
    iconset = Path(tempfile.mkdtemp()) / "app.iconset"
    iconset.mkdir(parents=True)
    specs = [
        (16, "icon_16x16.png"), (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"), (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"), (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"), (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"), (1024, "icon_512x512@2x.png"),
    ]
    for px, name in specs:
        subprocess.run(
            ["sips", "-z", str(px), str(px), str(master_png), "--out", str(iconset / name)],
            check=True, capture_output=True,
        )
    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset), "-o", str(BRANDING / "app.icns")],
        check=True,
    )
    shutil.rmtree(iconset.parent, ignore_errors=True)


def make_ico(master: QtGui.QImage) -> None:
    # Qt's ICO writer takes a single image; 256x256 is the max Windows uses.
    ico = master.scaled(256, 256, QtCore.Qt.KeepAspectRatio,
                         QtCore.Qt.SmoothTransformation)
    if not ico.save(str(BRANDING / "app.ico"), "ICO"):
        raise RuntimeError("QImage.save failed for app.ico (qico plugin missing?)")


def main() -> int:
    # A QGuiApplication is needed for image I/O plugins.
    from PySide6 import QtGui as _QtGui  # noqa
    app = QtGui.QGuiApplication.instance() or QtGui.QGuiApplication(sys.argv)
    BRANDING.mkdir(exist_ok=True)
    master = render_master()
    master_png = BRANDING / "app.png"
    master.save(str(master_png), "PNG")
    make_icns(master_png)
    make_ico(master)
    print(f"Wrote {master_png}, {BRANDING/'app.icns'}, {BRANDING/'app.ico'}")
    del app
    return 0


if __name__ == "__main__":
    sys.exit(main())
