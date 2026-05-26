# Changelog

All notable changes to this project are tracked in this file.
The format is loosely based on [Keep a Changelog](https://keepachangelog.com/),
and the project adheres to [Semantic Versioning](https://semver.org/).

## [0.6.1]

### Changed

- Bundled definitive good icons: every PR2 transportable good now has a
  dedicated PNG named after the English good name (Wheat, Fruit, Wood,
  Bricks, Corn, Sugar, Cotton, Hemp, Meat, Garments, Rope, Rum, Coffee,
  Cacao, Dyes, Tobacco, Spices, Wine, Tools, Settlers). The previous
  French placeholders from elzetia.com are gone.
- README, CHANGELOG and the `pr2_editor/icons.py` docstring updated for
  the new icons. README screenshots regenerated.

## [0.6.0] — first public release

Initial public release of the PR2 Trade Routes Editor: full `.ahr` codec,
PySide6 GUI, calibrated map, and standalone installers via PyInstaller.

### Highlights

- **`.ahr` codec** — byte-perfect decode/encode with regression fixtures, plus
  a builder that takes user-friendly JSON specs and produces a valid `.ahr`.
- **PySide6 GUI** — stops list with drag-drop reorder; goods table grouped in
  5 sections (Basic resources / Raw materials / Production goods / Colonial
  goods / Imported & colony); per-good Action (Auto/Excluded/Manual) and Mode
  (City/Warehouse); load+unload qty/price sliders with adaptive ranges from
  `pr2_config.json`; 💰 buttons that apply the city's recommended buy/sell
  price; multi-select checkboxes with auto-propagation of edits to every
  selected good.
- **Map view** — clickable Caribbean map (`Edit route` button, `Esc` exits).
  Hover for city details, left-click adds a stop, right-click removes one.
  The route is drawn with numbered badges and a dotted return-leg back to
  the start. Coordinates come from `pr2_map_coords.json`, produced once by
  `tools/calibrate_map.py`.
- **Manage cities dialog** (Tools → Manage cities…): per-game overrides for
  warehouse level, current nation, and recommended price per good per city.
- **Excluded styling** — Route-excluded goods read 🚫 *bold red strikethrough*,
  stop-excluded ⊘ *italic gray*, produced goods 🟢 prefix.
- **Theming** — global Qt stylesheet, accent buttons, light info card.
- **Installers** — PyInstaller spec for macOS (`.app`) and Windows (one-folder
  bundle). Bundled assets stay read-only; per-user state lives in the OS
  app-data directory.

### Known limitations

- PyInstaller output is unsigned. macOS asks for Right-click → Open on first
  launch; Windows SmartScreen will warn about an unknown publisher.
- Linux is not actively tested; the PyInstaller spec runs on Linux but no
  desktop integration files are shipped.
