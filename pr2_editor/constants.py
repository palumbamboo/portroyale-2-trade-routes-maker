"""Constants and reference paths for the package.

Two roots are tracked:

- ``WORKSPACE`` — read-only bundled assets (config, map image, map coords, icons).
  In development this is the repo root. When the app is frozen by PyInstaller it
  is the directory where PyInstaller extracted the bundled data.

- ``USER_DATA`` — writable per-user state. In development this is also the repo
  root so editing the project keeps using the local ``user_state.json`` and
  ``rotte/`` folders. When frozen it is an OS-appropriate app-data directory
  so the installed app can write without touching the bundle.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path


def _bundled_root() -> Path:
    """Folder that hosts the read-only bundled assets (config, map, icons)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        # PyInstaller extracts bundled data here at runtime.
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[1]


def _user_data_root() -> Path:
    """Folder for writable per-user data (user_state.json, saved routes…).

    In development we keep using the repo root so the dev iteration feels the
    same as before; when the app is frozen we switch to the OS app-data
    directory so the installed program never tries to write inside its bundle.
    """
    if not getattr(sys, "frozen", False):
        return Path(__file__).resolve().parents[1]
    app = "PR2RoutesEditor"
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / app
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home()) / app
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")) / app
    base.mkdir(parents=True, exist_ok=True)
    return base


WORKSPACE = _bundled_root()
USER_DATA = _user_data_root()

# Bundled (read-only)
CONFIG_PATH = WORKSPACE / "pr2_config.json"
MAP_IMAGE_PATH = WORKSPACE / "port-royal2-2-map.jpg"
MAP_COORDS_PATH = WORKSPACE / "pr2_map_coords.json"
ICONS_DIR = WORKSPACE / "icons"

# Writable (per-user)
USER_STATE_PATH = USER_DATA / "user_state.json"
ROUTES_DIR = USER_DATA / "rotte"

# .ahr format sentinels
QTY_MAX = 0xFFFF
WAREHOUSE_PRICE = 0xFFFFFFFF

# Per-stop actions for a good
ACTION_AUTO = 1
ACTION_EXCLUDED = 0
ACTION_MANUAL = 2

ACTION_LABEL = {
    ACTION_AUTO: "Auto",
    ACTION_EXCLUDED: "Excluded",
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
