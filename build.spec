# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the PR2 Trade Routes Editor.

Build (from the repo root, after installing the project with the dev extras):

    # macOS
    .venv/bin/pyinstaller --clean --noconfirm build.spec
    # Windows (PowerShell or cmd.exe)
    .venv\\Scripts\\pyinstaller.exe --clean --noconfirm build.spec

Output (under dist/):
    macOS:   dist/PR2 Routes Editor.app  (open with Finder, or `open` from terminal)
    Windows: dist/PR2RoutesEditor/PR2RoutesEditor.exe

The bundle ships read-only assets (pr2_config.json, the map image, calibrated
coords, icons). Per-user state (user_state.json, saved .ahr routes) lives in
the OS app-data folder:
    macOS:   ~/Library/Application Support/PR2RoutesEditor/
    Windows: %APPDATA%/PR2RoutesEditor/
constants.py resolves these paths automatically when sys.frozen is true.
"""
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve()

block_cipher = None

datas = [
    (str(ROOT / "pr2_config.json"),       "."),
    (str(ROOT / "pr2_map_coords.json"),   "."),
    (str(ROOT / "port-royal2-2-map.jpg"), "."),
    (str(ROOT / "icons"),                 "icons"),
]

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "unittest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# One-folder bundle. Faster to start than --onefile and avoids the
# anti-virus heuristics that flag self-extracting Windows binaries.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PR2RoutesEditor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                # GUI app, no console window on Windows
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PR2RoutesEditor",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="PR2 Routes Editor.app",
        bundle_identifier="com.palumbamboo.pr2_routes_editor",
        version="0.6.2",
        info_plist={
            "NSHighResolutionCapable": True,
            "CFBundleShortVersionString": "0.6.2",
            "CFBundleVersion": "0.6.2",
            # Avoid the OS quarantine asking for full disk access on macOS by
            # declaring a clean sandbox-friendly identity:
            "LSMinimumSystemVersion": "11.0",
        },
    )
