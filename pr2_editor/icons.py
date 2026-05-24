"""Risoluzione delle icone delle merci da disco."""
from __future__ import annotations

from PySide6 import QtGui

from .constants import ICONS_DIR

GOOD_ICON_FILE: dict[int, str | None] = {
    0:  "ble.png",            1:  "fruits.png",  2:  "bois.png",   3:  "briques.png",
    4:  "mais.png",           5:  "sucre.png",   6:  "cotton.png", 7:  "chanvre.png",
    8:  "viande.png",         9:  "vetements.png", 10: "cordes.png", 11: "rhum.png",
    12: "cafe.png",           13: "cacao.png",   14: "teinture.png", 15: "tabac.png",
    16: "textiles.png",       17: "pain.png",    18: "outils_en_metal.png", 19: "metal.png",
}


def good_icon(good_id: int) -> QtGui.QIcon:
    fname = GOOD_ICON_FILE.get(good_id)
    if fname:
        p = ICONS_DIR / fname
        if p.exists():
            return QtGui.QIcon(str(p))
    return QtGui.QIcon()
