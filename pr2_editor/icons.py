"""Resolves good icons from disk (loaded from the bundled icons/ folder)."""
from __future__ import annotations

from PySide6 import QtGui

from .constants import ICONS_DIR

GOOD_ICON_FILE: dict[int, str | None] = { 
    0:  "wheat.png",  1:  "fruit.png",    2:  "wood.png",   3:  "bricks.png",
    4:  "corn.png",   5:  "sugar.png",    6:  "cotton.png", 7:  "hemp.png",
    8:  "meat.png",   9:  "garments.png", 10: "rope.png",   11: "rum.png",
    12: "coffee.png", 13: "cacao.png",    14: "dyes.png",   15: "tobacco.png",
    16: "spices.png", 17: "wine.png",     18: "tools.png",  19: "settlers.png",
}


def good_icon(good_id: int) -> QtGui.QIcon:
    fname = GOOD_ICON_FILE.get(good_id)
    if fname:
        p = ICONS_DIR / fname
        if p.exists():
            return QtGui.QIcon(str(p))
    return QtGui.QIcon()
