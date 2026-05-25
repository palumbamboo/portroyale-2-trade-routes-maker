"""Map window: standalone window hosting the MapView plus a zoom toolbar."""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ..store import Store
from .map_view import MapView


class MapWindow(QtWidgets.QMainWindow):
    """Top-level window with the map; emits city_clicked when a city is clicked."""

    city_clicked = QtCore.Signal(int)                       # left-click
    city_right_clicked = QtCore.Signal(int, QtCore.QPoint)  # right-click + global pos

    def __init__(self, store: Store, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Map view")
        self.resize(1200, 900)

        self.map_view = MapView(store)
        self.map_view.city_clicked.connect(self.city_clicked)
        self.map_view.city_right_clicked.connect(self.city_right_clicked)
        self.setCentralWidget(self.map_view)

        tb = self.addToolBar("Map")
        a_fit = tb.addAction("Fit window")
        a_fit.triggered.connect(self.map_view.fit_to_view)
        a_reset = tb.addAction("Reset zoom")
        a_reset.triggered.connect(self.map_view.reset_zoom)
        tb.addSeparator()
        hint = QtWidgets.QLabel(
            " <i>Click on a city to add it to the route. Hover to see details. "
            "Ctrl + scroll = zoom. Drag empty area to pan.</i> ")
        hint.setTextFormat(QtCore.Qt.RichText)
        tb.addWidget(hint)

        self.statusBar().showMessage("Hover a city for details. Click to add to the current route.")

    def set_route(self, city_ids: list[int]) -> None:
        self.map_view.set_route(city_ids)

    def refresh_tooltips(self) -> None:
        self.map_view.refresh_tooltips()
