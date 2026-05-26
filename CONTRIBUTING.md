# Contributing

Thanks for the interest! This is a hobby project, but PRs and issues are
welcome.

## Getting started

```bash
git clone https://github.com/palumbamboo/portroyale-2-trade-routes-maker
cd portroyale-2-trade-routes-maker

# Create a venv with the project + dev extras.
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -e ".[dev]"

# Launch the GUI:
.venv/bin/python -m pr2_editor
```

## Running the tests

```bash
# Unit tests
.venv/bin/pytest

# Regression on the .ahr codec fixtures
python ahr.py test rotte/test
```

Both must stay green before opening a PR.

## Coding conventions

- Plain `pathlib.Path` everywhere; no string paths.
- All user-facing strings in English. The data files (`pr2_config.json`,
  `pr2_map_coords.json`) keep English keys and values.
- Don't write to `user_state.json` from a dev script. Any throw-away script
  that needs a `Store` must point `Store(user_state_path=…)` at a `tempfile`
  path (see `tools/calibrate_map.py` for the pattern).
- Visual changes: drop a screenshot in the PR. The fastest way to take one
  is to install `PySide6` headless and use `QT_QPA_PLATFORM=offscreen`.

## Reporting bugs

Use the [issue tracker](https://github.com/palumbamboo/portroyale-2-trade-routes-maker/issues).
For codec bugs, please attach the offending `.ahr` so the regression suite
can grow.

## Building installers

See the *Building installers* section in the README.
