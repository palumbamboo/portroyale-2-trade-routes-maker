"""Costanti e path di riferimento del package."""
from __future__ import annotations
from pathlib import Path

# Root del repository (parents[1] = la cartella che contiene pr2_editor/)
WORKSPACE = Path(__file__).resolve().parents[1]
CONFIG_PATH = WORKSPACE / "pr2_config.json"
USER_STATE_PATH = WORKSPACE / "user_state.json"
ICONS_DIR = WORKSPACE / "icons"
ROUTES_DIR = WORKSPACE / "rotte"

# Sentinelle del formato .ahr
QTY_MAX = 0xFFFF
WAREHOUSE_PRICE = 0xFFFFFFFF

# Azioni per merce su uno stop
ACTION_AUTO = 1
ACTION_EXCLUDED = 0
ACTION_MANUAL = 2

ACTION_LABEL = {
    ACTION_AUTO: "Automatica",
    ACTION_EXCLUDED: "Esclusa qui",
    ACTION_MANUAL: "Manuale",
}
MODE_LABEL = {"city": "Città", "warehouse": "Magazzino"}

# Nazioni selezionabili nella dialog di gestione città (include "pirata", non presente nel config).
NATIONS_AVAILABLE = ["spagna", "francia", "inghilterra", "olanda", "pirata"]

# Conversione livello magazzino -> tonnellate di capienza
WAREHOUSE_TONS_PER_LEVEL = 800

# Range pratici per gli slider nella GoodsTable.
# Sopra QTY_SLIDER_MAX: la quantita' diventa QTY_MAX (sentinella "MAX" nel formato).
# Sopra PRICE_SLIDER_MAX: lo spinbox di overflow consente fino a 999_999.
QTY_SLIDER_MAX = 1600
PRICE_SLIDER_MAX = 500

# Divisione delle 20 merci in 5 sezioni mostrate nella GoodsTable.
# Ogni sezione ha 4 merci consecutive per good_id.
GOOD_SECTIONS: list[tuple[str, list[int]]] = [
    ("Risorse base",          [0, 1, 2, 3]),
    ("Materie prime",         [4, 5, 6, 7]),
    ("Beni prodotti",         [8, 9, 10, 11]),
    ("Beni coloniali",        [12, 13, 14, 15]),
    ("Importazioni e coloni", [16, 17, 18, 19]),
]
