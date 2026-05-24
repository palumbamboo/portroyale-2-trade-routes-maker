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
