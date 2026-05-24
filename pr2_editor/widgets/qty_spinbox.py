"""Widget custom: QtyMaxSpinBox (sentinella MAX = 0xFFFF) e _ModifierToolButton (click + modificatori)."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ..constants import QTY_MAX


class QtyMaxSpinBox(QtWidgets.QSpinBox):
    """QSpinBox che mostra 'MAX' quando il valore e' 0xFFFF."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(0, QTY_MAX)

    def textFromValue(self, value: int) -> str:
        if value == QTY_MAX:
            return "MAX"
        return str(value)

    def valueFromText(self, text: str) -> int:
        if text.strip().upper() == "MAX":
            return QTY_MAX
        try:
            return int(text)
        except ValueError:
            return 0

    def validate(self, text: str, pos: int):
        if text.strip().upper() in ("", "M", "MA", "MAX"):
            return (QtGui.QValidator.Acceptable, text, pos)
        try:
            n = int(text)
            if 0 <= n <= QTY_MAX:
                return (QtGui.QValidator.Acceptable, text, pos)
        except ValueError:
            pass
        return (QtGui.QValidator.Invalid, text, pos)


class _ModifierToolButton(QtWidgets.QToolButton):
    """ToolButton che emette i modificatori al click."""

    clicked_with_mods = QtCore.Signal(QtCore.Qt.KeyboardModifiers)

    def mouseReleaseEvent(self, ev: QtGui.QMouseEvent) -> None:
        mods = ev.modifiers()
        super().mouseReleaseEvent(ev)
        if self.rect().contains(ev.pos()):
            self.clicked_with_mods.emit(mods)
