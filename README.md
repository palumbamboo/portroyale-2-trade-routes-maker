# Port Royale 2 — Trade Routes Maker

Editor for the trade routes (`.ahr` files) of **Port Royale 2 — Empire & Pirates**.
Includes a format decoder/encoder, a JSON → `.ahr` builder, and a desktop GUI to create and edit routes without touching the game.

## Status

- ✅ `.ahr` format fully reverse-engineered (header, route exclusions, per-good actions, load/unload modes, quantities, threshold prices, city + warehouse).
- ✅ Full mapping: 60 cities (id 0-59 with name, nation, role V/G, produced goods), 20 goods (id 0-19 with name, min/market/max prices, recommended buy/sell prices).
- ✅ Python encoder/decoder with byte-perfect roundtrip (regression fixtures).
- ✅ JSON → `.ahr` builder, validated in-game.
- ✅ PySide6 GUI with inline table editing of all goods.
- 🚧 Standalone Windows `.exe` packaging via PyInstaller.

## Folder layout

```
.
├── ahr.py                    # decoder/encoder/builder + CLI (standalone library)
├── pr2_editor/               # GUI package (PySide6)
│   ├── __main__.py           #   `python -m pr2_editor`
│   ├── app.py                #   main(): QApplication + MainWindow
│   ├── constants.py
│   ├── icons.py
│   ├── store.py              #   config + user_state (per-game overrides)
│   ├── route.py              #   current-route model
│   ├── main_window.py
│   └── widgets/
│       ├── goods_table.py
│       ├── add_stop_dialog.py
│       ├── manage_cities_dialog.py
│       ├── map_view.py       #   QGraphicsView with map + city markers
│       ├── map_window.py     #   standalone map window
│       └── row_widgets.py    #   QtySlider, PriceSlider, _ModifierToolButton
├── tools/
│   └── calibrate_map.py      # one-shot tool to record city (x, y) on the map
├── tests/                    # pytest: Store setters, Route model, .ahr roundtrip
├── pr2_config.json           # static config: 20 goods + 60 cities (read-only)
├── pr2_map_coords.json       # city -> (x, y) on the map image (produced by calibrate_map.py)
├── user_state.json           # local per-game state (gitignored)
├── pyproject.toml            # PySide6 deps + dev pytest
├── README.md
├── port-royal2-2-map.jpg     # reference map
├── icons/                    # good icons (French placeholders from elzetia.com)
└── rotte/                    # data folder (legacy name from the original project)
    ├── input/                # .ahr routes exported from the game (gitignored)
    ├── parsed/               # decoded JSON (gitignored, derived)
    ├── built/                # builder output (gitignored, derived)
    ├── build/                # user-friendly JSON specs for the builder
    │   └── example-route.json
    └── test/                 # .ahr fixtures for regression tests
        └── fixture_rotta01.ahr
```

## Environment setup

```bash
# Create a venv with Python 3.13 (compatible with PySide6) and install deps
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
```

## CLI usage (`ahr.py`)

```bash
# Decode an .ahr into inspectable JSON
python ahr.py decode "route.ahr" "route.json"

# From raw JSON (output of decode) to .ahr
python ahr.py encode "route.json" "route.ahr"

# From user-friendly JSON to .ahr (see rotte/build/example-route.json)
python ahr.py build "spec.json" "route.ahr"

# Roundtrip identity check
python ahr.py roundtrip "route.ahr"

# List the city_ids of the stops (annotated with names if pr2_config.json is present)
python ahr.py cities "route.ahr"

# Decode every .ahr in a folder
python ahr.py decode-dir rotte/input rotte/parsed

# Regression test (roundtrip over every .ahr in a folder)
python ahr.py test rotte/test
```

## GUI usage

```bash
.venv/bin/python -m pr2_editor
# or, after `pip install -e .`:
pr2-editor
```

Features:
- **Stops panel** (drag-drop to reorder) + global exclusions checklist.
- **Goods table** grouped in 5 sections (Basic resources / Raw materials / Production goods / Colonial goods / Imported & colony), with inline editing for every good: action (auto/excluded/manual), load (mode/qty/price), unload (same).
- **Per-row sliders** for qty (0-2000 then MAX) and price (per-good range from `pr2_config.json`); the spinbox next to each slider is always editable for overrides.
- **Section quick commands**: each section has Action / Mode / Apply-recommended-prices / Qty+Apply, acting on the 4 goods in the section.
- **Multi-select**: tick the checkbox on any row to add goods to a bulk-action bar that appears above the table, with the same 4 quick commands acting on the selection.
- **Visual cues** for excluded goods: route-excluded (strikethrough red), stop-excluded (italic gray).
- **💰 buttons** apply the recommended price with Ctrl/Shift modifiers (this good only, both sides, all manual, etc.).
- **Context menus** on price (Min/Market/Max), on good (copy/paste/reset), on stop (copy/paste/remove).
- `Ctrl+S` / `Ctrl+Shift+S` to save / save as.
- **Tools → Map view**: clickable map of the Caribbean. Hover a city to preview name / nation / role / produced goods / warehouse; click to add it to the current route. Stops are drawn in order with connecting lines and numbered badges. Requires `pr2_map_coords.json` (see *Map calibration* below).
- **Tools → Manage cities**: edit per-game overrides (warehouse level, current nation, recommended-price overrides per good).
- **Filter** input above the goods table hides goods that don't match the typed text. **Green dot** prefix on goods produced by the current stop's city.

## Map calibration

The map view requires per-city coordinates on the image. Generate them once with:

```bash
.venv/bin/python tools/calibrate_map.py
```

The tool walks city-by-city (60 in total): click on the matching city on the map image, the (x, y) is recorded. Press *Save & quit* when done. Re-run any time to fix or extend. Output is written to `pr2_map_coords.json` and committed to the repo so other clones don't need to redo it.

## Tests

```bash
# .ahr codec regression
python ahr.py test rotte/test

# pytest suite (Store, Route, roundtrip)
.venv/bin/pytest
```

## `.ahr` format (summary)

```
Header (11 bytes):
  magic        4 bytes  = 0x41 0x04 0x00 0x00 ("A" + 0x04)
  nstops       1 byte   number of stops (1-16)
  capacity     1 byte   ceil(nstops/4)*4, capped at 16
  bitmap       5 bytes  route exclusions (1 bit = 1 active good)

Stop (426 bytes, repeated nstops times):
  display_order   20 bytes   permutation 0..19 (manuals on top in the UI)
  actions[20]     u32 LE     0=excluded, 1=auto, 2=manual
  trades[20]      16 bytes each:
    load_price    u32 LE     city threshold (gold/ton); 0xFFFFFFFF = "from warehouse"
    load_qty      u16 LE     quantity (0xFFFF = "max")
    load_aux      u16 LE     snapshot residue, preserved for roundtrip
    unload_price  u32 LE     same as above for unload
    unload_qty    u16 LE
    unload_aux    u16 LE
  trailer         6 bytes    city_id, 0x00, 0x21, 0x00, start_flag, 0x00
```

## Notes

- Cities can change nation during a game: the `nation` field in `pr2_config.json` is the initial nation at the start of a new game. Per-game overrides live in `user_state.json` (gitignored).
- Per-good recommended buy/sell prices are defined globally in `pr2_config.json` and can be overridden per city in `user_state.json` via Tools → Manage cities.
- Good icons come from [elzetia.com](https://elzetia.com) — they are French and a few are used as placeholders for the PR2-specific goods (Spices, Wine, Settlers).
