"""Widget for the GoodsTable cells: qty/price sliders + modifier-click button."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ..constants import QTY_MAX


class _NoWheelSlider(QtWidgets.QSlider):
    """QSlider that ignores wheel events so accidental scrolls don't change the value."""

    def wheelEvent(self, ev: QtGui.QWheelEvent) -> None:
        ev.ignore()


class _NoWheelSpinBox(QtWidgets.QSpinBox):
    """QSpinBox that ignores wheel events."""

    def wheelEvent(self, ev: QtGui.QWheelEvent) -> None:
        ev.ignore()


class _QtyEditSpinBox(QtWidgets.QSpinBox):
    """QSpinBox that shows 'MAX' when the value equals QTY_MAX (0xFFFF sentinel).

    Wheel events are ignored to avoid accidental changes while scrolling the table.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(0, QTY_MAX)

    def wheelEvent(self, ev: QtGui.QWheelEvent) -> None:
        ev.ignore()

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
        s = text.strip().upper()
        if s in ("", "M", "MA", "MAX"):
            return (QtGui.QValidator.Acceptable, text, pos)
        try:
            n = int(text)
            if 0 <= n <= QTY_MAX:
                return (QtGui.QValidator.Acceptable, text, pos)
        except ValueError:
            pass
        return (QtGui.QValidator.Invalid, text, pos)


class QtySlider(QtWidgets.QWidget):
    """Slider 0..2001 (al fondo = MAX) + spinbox editabile.

    - Posizione 0..2000 → valore esatto.
    - Posizione 2001 → sentinella MAX (QTY_MAX = 0xFFFF, "max nave/magazzino").
    - Lo spinbox accetta valori arbitrari 0..QTY_MAX, mostra "MAX" alla sentinella;
      è sempre la fonte di verità (lo slider si attesta al limite più vicino se
      il valore è > 2000 ma < QTY_MAX, caso anomalo).
    """

    valueChanged = QtCore.Signal(int)

    PRECISE_MAX = 2000      # ultimo valore lineare
    MAX_POSITION = 2001     # posizione speciale = QTY_MAX

    def __init__(self, parent=None):
        super().__init__(parent)
        self._suppress = False

        h = QtWidgets.QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)

        self.slider = _NoWheelSlider(QtCore.Qt.Horizontal)
        self.slider.setRange(0, self.MAX_POSITION)
        self.slider.setSingleStep(50)
        self.slider.setPageStep(200)
        self.slider.setMinimumWidth(50)
        self.slider.setToolTip("Slider 0–2000 t; end of travel = MAX")
        self.slider.valueChanged.connect(self._on_slider_changed)
        h.addWidget(self.slider, 1)

        self.spin = _QtyEditSpinBox()
        self.spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.spin.setAlignment(QtCore.Qt.AlignRight)
        self.spin.setMinimumWidth(46)
        self.spin.setMaximumWidth(54)
        self.spin.setToolTip("Type a number or 'MAX'")
        self.spin.valueChanged.connect(self._on_spin_changed)
        # Force opaque background so the slider track doesn't bleed through
        self.spin.setAttribute(QtCore.Qt.WA_OpaquePaintEvent, True)
        h.addWidget(self.spin)

    def value(self) -> int:
        return int(self.spin.value())

    def setValue(self, v: int) -> None:
        v = max(0, min(int(v), QTY_MAX))
        if v == int(self.spin.value()):
            return
        self._suppress = True
        try:
            self.spin.setValue(v)
            self._sync_slider_from_value(v)
        finally:
            self._suppress = False

    def _sync_slider_from_value(self, v: int) -> None:
        if v == QTY_MAX:
            self.slider.setValue(self.MAX_POSITION)
        elif v >= self.PRECISE_MAX:
            self.slider.setValue(self.PRECISE_MAX)
        else:
            self.slider.setValue(int(v))

    def _on_slider_changed(self, pos: int) -> None:
        if self._suppress:
            return
        value = QTY_MAX if pos == self.MAX_POSITION else pos
        self._suppress = True
        try:
            self.spin.setValue(value)
        finally:
            self._suppress = False
        self.valueChanged.emit(value)

    def _on_spin_changed(self, v: int) -> None:
        if self._suppress:
            return
        self._suppress = True
        try:
            self._sync_slider_from_value(v)
        finally:
            self._suppress = False
        self.valueChanged.emit(int(v))

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        self.slider.setEnabled(enabled)
        self.spin.setEnabled(enabled)


class PriceSlider(QtWidgets.QWidget):
    """Slider tra price_min e price_max della merce + spinbox editabile.

    Il range dello slider è specifico per merce e va configurato con
    `set_slider_range(min, max)`. Lo spinbox accetta sempre valori arbitrari
    fino a 999_999 (utile per override anomali).
    """

    valueChanged = QtCore.Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._suppress = False
        self._slider_min = 0
        self._slider_max = 1

        h = QtWidgets.QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)

        self.slider = _NoWheelSlider(QtCore.Qt.Horizontal)
        self.slider.setRange(0, 1)
        self.slider.setMinimumWidth(50)
        self.slider.valueChanged.connect(self._on_slider_changed)
        h.addWidget(self.slider, 1)

        self.spin = _NoWheelSpinBox()
        self.spin.setRange(0, 999_999)
        self.spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.spin.setAlignment(QtCore.Qt.AlignRight)
        self.spin.setMinimumWidth(48)
        self.spin.setMaximumWidth(58)
        self.spin.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.spin.setToolTip("Type any value (overrides the slider range)")
        self.spin.valueChanged.connect(self._on_spin_changed)
        self.spin.setAttribute(QtCore.Qt.WA_OpaquePaintEvent, True)
        h.addWidget(self.spin)

    def set_slider_range(self, min_val: int, max_val: int) -> None:
        self._slider_min = max(0, int(min_val))
        self._slider_max = max(self._slider_min + 1, int(max_val))
        self.slider.setRange(self._slider_min, self._slider_max)
        span = self._slider_max - self._slider_min
        # Step adattati al range della merce: ~1% del range, minimo 1.
        self.slider.setSingleStep(max(1, span // 100))
        self.slider.setPageStep(max(5, span // 10))
        self.slider.setToolTip(f"Slider {self._slider_min}–{self._slider_max} €/t")
        self._sync_slider_from_value(self.spin.value())

    def value(self) -> int:
        return int(self.spin.value())

    def setValue(self, v: int) -> None:
        v = max(0, min(int(v), 999_999))
        if v == int(self.spin.value()):
            return
        self._suppress = True
        try:
            self.spin.setValue(v)
            self._sync_slider_from_value(v)
        finally:
            self._suppress = False

    def _sync_slider_from_value(self, v: int) -> None:
        clamped = max(self._slider_min, min(int(v), self._slider_max))
        self.slider.setValue(clamped)

    def _on_slider_changed(self, v: int) -> None:
        if self._suppress:
            return
        self._suppress = True
        try:
            self.spin.setValue(int(v))
        finally:
            self._suppress = False
        self.valueChanged.emit(int(v))

    def _on_spin_changed(self, v: int) -> None:
        if self._suppress:
            return
        self._suppress = True
        try:
            self._sync_slider_from_value(v)
        finally:
            self._suppress = False
        self.valueChanged.emit(int(v))

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        self.slider.setEnabled(enabled)
        self.spin.setEnabled(enabled)


class _ModifierToolButton(QtWidgets.QToolButton):
    """ToolButton che emette i modificatori (Ctrl/Shift) al click."""

    clicked_with_mods = QtCore.Signal(QtCore.Qt.KeyboardModifiers)

    def mouseReleaseEvent(self, ev: QtGui.QMouseEvent) -> None:
        mods = ev.modifiers()
        super().mouseReleaseEvent(ev)
        if self.rect().contains(ev.pos()):
            self.clicked_with_mods.emit(mods)
