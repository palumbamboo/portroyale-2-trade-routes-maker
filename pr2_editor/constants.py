"""Constants and reference paths for the package."""
from __future__ import annotations
from pathlib import Path

# Repository root (parents[1] = the folder containing pr2_editor/)
WORKSPACE = Path(__file__).resolve().parents[1]
CONFIG_PATH = WORKSPACE / "pr2_config.json"
USER_STATE_PATH = WORKSPACE / "user_state.json"
ICONS_DIR = WORKSPACE / "icons"
ROUTES_DIR = WORKSPACE / "rotte"

# .ahr format sentinels
QTY_MAX = 0xFFFF
WAREHOUSE_PRICE = 0xFFFFFFFF

# Per-stop actions for a good
ACTION_AUTO = 1
ACTION_EXCLUDED = 0
ACTION_MANUAL = 2

ACTION_LABEL = {
    ACTION_AUTO: "Auto",
    ACTION_EXCLUDED: "Excluded here",
    ACTION_MANUAL: "Manual",
}
MODE_LABEL = {"city": "City", "warehouse": "Warehouse"}

# Nations selectable in the manage-cities dialog (data values; English now).
NATIONS_AVAILABLE = ["spain", "france", "england", "netherlands", "pirate"]
NATION_LABELS = {
    "spain": "Spain",
    "france": "France",
    "england": "England",
    "netherlands": "Netherlands",
    "pirate": "Pirate",
}

# Warehouse level -> tons of capacity
WAREHOUSE_TONS_PER_LEVEL = 800

# 20 goods divided into 5 sections shown in the GoodsTable.
# Each section has 4 consecutive goods by good_id.
GOOD_SECTIONS: list[tuple[str, list[int]]] = [
    ("Basic resources",      [0, 1, 2, 3]),
    ("Raw materials",        [4, 5, 6, 7]),
    ("Production goods",     [8, 9, 10, 11]),
    ("Colonial goods",       [12, 13, 14, 15]),
    ("Imported & colony",    [16, 17, 18, 19]),
]
