"""Fixture pytest condivise."""
from __future__ import annotations
from pathlib import Path

import pytest
from PySide6 import QtCore

from pr2_editor.store import Store


@pytest.fixture(scope="session")
def qt_app():
    """QCoreApplication unica per la sessione (non serve QApplication: nessun widget nei test)."""
    app = QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])
    yield app


@pytest.fixture
def store(tmp_path: Path, qt_app):
    """Store con user_state_path su tempfile (non sporca user_state.json reale)."""
    user_state_path = tmp_path / "user_state.json"
    return Store(user_state_path=user_state_path)
