"""Widget per le celle della GoodsTable: slider per quantità/prezzo + bottone modificatori."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ..constants import (
    PRICE_SLIDER_MAX,
    QTY_MAX,
    QTY_SLIDER_MAX,
)


class QtySlider(QtWidgets.QWidget):
    """Slider 0..QTY_SLIDER_MAX + label numerica + checkbox MAX (per la sentinella 0xFFFF).

    Per quantità nel range 0..QTY_SLIDER_MAX usa lo slider; per il valore
    speciale QTY_MAX (max nave/magazzino) usa il checkbox MAX, che mette lo
    slider in stato disabilitato.
    """

    valueChanged = QtCore.Signal(int)  # emette il valore corrente (intero in 0..QTY_MAX)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._suppress = False
        self._value = 0

        h = QtWidgets.QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)

        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setRange(0, QTY_SLIDER_MAX)
        self.slider.setSingleStep(50)
        self.slider.setPageStep(200)
        self.slider.valueChanged.connect(self._on_slider_changed)
        h.addWidget(self.slider, 1)

        self.lbl = QtWidgets.QLabel("0")
        self.lbl.setMinimumWidth(36)
        self.lbl.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        h.addWidget(self.lbl)

        self.cb_max = QtWidgets.QCheckBox("MAX")
        self.cb_max.toggled.connect(self._on_max_toggled)
        h.addWidget(self.cb_max)

    def value(self) -> int:
        return self._value

    def setValue(self, v: int) -> None:
        v = max(0, min(int(v), QTY_MAX))
        if v == self._value:
            return
        self._value = v
        self._suppress = True
        try:
            if v == QTY_MAX:
                self.cb_max.setChecked(True)
                self.slider.setEnabled(False)
                self.lbl.setText("MAX")
            else:
                self.cb_max.setChecked(False)
                self.slider.setEnabled(self.isEnabled())
                self.slider.setValue(min(v, QTY_SLIDER_MAX))
                self.lbl.setText(str(v))
        finally:
            self._suppress = False

    def _on_slider_changed(self, v: int) -> None:
        if self._suppress or self.cb_max.isChecked():
            return
        self._value = int(v)
        self.lbl.setText(str(v))
        self.valueChanged.emit(self._value)

    def _on_max_toggled(self, checked: bool) -> None:
        if self._suppress:
            return
        if checked:
            self._value = QTY_MAX
            self.slider.setEnabled(False)
            self.lbl.setText("MAX")
        else:
            self._value = int(self.slider.value())
            self.slider.setEnabled(self.isEnabled())
            self.lbl.setText(str(self._value))
        self.valueChanged.emit(self._value)

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        # Lo slider resta disabilitato se è attivo MAX, anche se il widget è enabled.
        self.slider.setEnabled(enabled and not self.cb_max.isChecked())
        self.cb_max.setEnabled(enabled)


class PriceSlider(QtWidgets.QWidget):
    """Slider 0..PRICE_SLIDER_MAX + spinbox compatto (per valori oltre il range slider).

    Lo spinbox è la fonte di verità: lo slider riflette il valore quando è
    entro range, altrimenti si attesta al massimo (lo spinbox accetta fino a
    999_999 per i casi atipici).
    """

    valueChanged = QtCore.Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._suppress = False

        h = QtWidgets.QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)

        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setRange(0, PRICE_SLIDER_MAX)
        self.slider.setSingleStep(5)
        self.slider.setPageStep(20)
        self.slider.valueChanged.connect(self._on_slider_changed)
        h.addWidget(self.slider, 1)

        self.spin = QtWidgets.QSpinBox()
        self.spin.setRange(0, 999_999)
        self.spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.spin.setAlignment(QtCore.Qt.AlignRight)
        self.spin.setMinimumWidth(60)
        self.spin.setMaximumWidth(80)
        self.spin.valueChanged.connect(self._on_spin_changed)
        # Click destro sullo spinbox → context menu (gestito esternamente)
        self.spin.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        h.addWidget(self.spin)

    def value(self) -> int:
        return int(self.spin.value())

    def setValue(self, v: int) -> None:
        v = max(0, min(int(v), 999_999))
        if v == self.spin.value() and self.slider.value() == min(v, PRICE_SLIDER_MAX):
            return
        self._suppress = True
        try:
            self.spin.setValue(v)
            self.slider.setValue(min(v, PRICE_SLIDER_MAX))
        finally:
            self._suppress = False

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
            self.slider.setValue(min(int(v), PRICE_SLIDER_MAX))
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
