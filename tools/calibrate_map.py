"""Map coordinate calibration tool.

Walks city-by-city through the 60 cities in pr2_config.json. For each one,
click on the city on the map image; the (x, y) in image-space is recorded.
Output: pr2_map_coords.json with {"city_key": [x, y], ...}.

Run from repo root:
    .venv/bin/python tools/calibrate_map.py

Controls:
    Left-click on the map: record this city's position, advance to next.
    "Skip" button: leave the current city without coords (can come back later).
    "Previous" / "Next" buttons: navigate without recording.
    "Save & quit": write pr2_map_coords.json and close.

If pr2_map_coords.json already exists, it is loaded as a starting point so you
can resume / fix up a previous session.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

WORKSPACE = Path(__file__).resolve().parents[1]
CONFIG_PATH = WORKSPACE / "pr2_config.json"
MAP_PATH = WORKSPACE / "port-royal2-2-map.jpg"
COORDS_PATH = WORKSPACE / "pr2_map_coords.json"

MARKER_RADIUS = 6
ACTIVE_MARKER_RADIUS = 10


class MapClickArea(QtWidgets.QLabel):
    """QLabel showing the map image; emits a signal on click with image-space coordinates."""

    clicked = QtCore.Signal(int, int)  # x, y in image coordinates

    def __init__(self, pixmap: QtGui.QPixmap, parent=None):
        super().__init__(parent)
        self._pixmap = pixmap
        self._coords: dict[str, tuple[int, int]] = {}
        self._active_key: str | None = None
        self.setPixmap(pixmap)
        self.setMouseTracking(True)

    def set_coords(self, coords: dict[str, tuple[int, int]]) -> None:
        self._coords = dict(coords)
        self._repaint_overlay()

    def set_active(self, key: str | None) -> None:
        self._active_key = key
        self._repaint_overlay()

    def _repaint_overlay(self) -> None:
        # Compose markers on a copy of the base pixmap
        composed = QtGui.QPixmap(self._pixmap)
        painter = QtGui.QPainter(composed)
        try:
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
            pen = QtGui.QPen(QtGui.QColor(20, 20, 20))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(QtGui.QColor(255, 220, 60, 220))
            for k, (x, y) in self._coords.items():
                r = ACTIVE_MARKER_RADIUS if k == self._active_key else MARKER_RADIUS
                painter.drawEllipse(QtCore.QPoint(int(x), int(y)), r, r)
                if k == self._active_key:
                    painter.setBrush(QtGui.QColor(80, 200, 80, 220))
        finally:
            painter.end()
        self.setPixmap(composed)

    def mousePressEvent(self, ev: QtGui.QMouseEvent) -> None:
        if ev.button() == QtCore.Qt.LeftButton:
            # The QLabel is shown at native pixmap size, so widget coords == image coords.
            p = ev.position().toPoint()
            self.clicked.emit(p.x(), p.y())


class CalibrationDialog(QtWidgets.QDialog):
    def __init__(self, cities: list[dict], coords: dict[str, tuple[int, int]],
                 pixmap: QtGui.QPixmap, parent=None):
        super().__init__(parent)
        self.cities = cities
        self.coords = dict(coords)
        self._current_idx = self._first_pending_index()
        self.setWindowTitle("Map calibration — Port Royale 2")
        self.resize(1700, 1100)
        self._build(pixmap)
        self._refresh_ui()

    def _first_pending_index(self) -> int:
        for i, c in enumerate(self.cities):
            if c["key"] not in self.coords:
                return i
        return 0

    def _build(self, pixmap: QtGui.QPixmap):
        layout = QtWidgets.QHBoxLayout(self)

        # --- left side: instructions + list + controls ---
        left = QtWidgets.QWidget()
        left.setMaximumWidth(300)
        lv = QtWidgets.QVBoxLayout(left)

        self.lbl_progress = QtWidgets.QLabel("")
        self.lbl_progress.setStyleSheet("font-size: 13pt;")
        lv.addWidget(self.lbl_progress)

        self.lbl_city = QtWidgets.QLabel("")
        self.lbl_city.setStyleSheet("font-size: 16pt; font-weight: bold;")
        lv.addWidget(self.lbl_city)

        self.lbl_meta = QtWidgets.QLabel("")
        self.lbl_meta.setWordWrap(True)
        lv.addWidget(self.lbl_meta)

        self.lst = QtWidgets.QListWidget()
        self.lst.currentRowChanged.connect(self._on_list_select)
        for c in self.cities:
            it = QtWidgets.QListWidgetItem("")
            it.setData(QtCore.Qt.UserRole, c["key"])
            self.lst.addItem(it)
        lv.addWidget(self.lst, 1)

        h = QtWidgets.QHBoxLayout()
        b_prev = QtWidgets.QPushButton("Previous")
        b_prev.clicked.connect(self._prev_city)
        b_next = QtWidgets.QPushButton("Next")
        b_next.clicked.connect(self._next_city)
        h.addWidget(b_prev); h.addWidget(b_next)
        lv.addLayout(h)

        h = QtWidgets.QHBoxLayout()
        b_skip = QtWidgets.QPushButton("Skip (clear)")
        b_skip.setToolTip("Remove the current city's coords (mark as pending)")
        b_skip.clicked.connect(self._skip_city)
        h.addWidget(b_skip)
        lv.addLayout(h)

        bb = QtWidgets.QDialogButtonBox()
        b_save = bb.addButton("Save && quit", QtWidgets.QDialogButtonBox.AcceptRole)
        b_cancel = bb.addButton("Quit without saving", QtWidgets.QDialogButtonBox.RejectRole)
        b_save.clicked.connect(self._save_and_quit)
        b_cancel.clicked.connect(self.reject)
        lv.addWidget(bb)

        layout.addWidget(left, 0)

        # --- right side: map in scroll area ---
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(False)
        self.map_area = MapClickArea(pixmap)
        self.map_area.set_coords(self.coords)
        self.map_area.clicked.connect(self._on_map_click)
        scroll.setWidget(self.map_area)
        layout.addWidget(scroll, 1)

    def _refresh_ui(self):
        n_done = len(self.coords)
        total = len(self.cities)
        self.lbl_progress.setText(f"Done: {n_done}/{total}")
        if not self.cities:
            return
        idx = max(0, min(self._current_idx, total - 1))
        c = self.cities[idx]
        coord_str = ""
        if c["key"] in self.coords:
            x, y = self.coords[c["key"]]
            coord_str = f"<br>recorded at ({x}, {y})"
        self.lbl_city.setText(f"{c['id']:>2}. {c['name']}")
        nation = c.get("nation", "?")
        role = c.get("role") or "—"
        self.lbl_meta.setText(
            f"<i>Click on the map</i> to place this city.<br>"
            f"nation: {nation} &nbsp; role: {role}{coord_str}"
        )
        # update list rows
        for i, ci in enumerate(self.cities):
            it = self.lst.item(i)
            mark = "✓" if ci["key"] in self.coords else "·"
            it.setText(f"{mark} {ci['id']:>2}. {ci['name']}")
            font = it.font()
            font.setBold(i == idx)
            it.setFont(font)
        was = self.lst.blockSignals(True)
        try:
            self.lst.setCurrentRow(idx)
        finally:
            self.lst.blockSignals(was)
        self.map_area.set_active(c["key"])

    def _on_list_select(self, row: int):
        if 0 <= row < len(self.cities):
            self._current_idx = row
            self._refresh_ui()

    def _on_map_click(self, x: int, y: int):
        c = self.cities[self._current_idx]
        self.coords[c["key"]] = (int(x), int(y))
        self.map_area.set_coords(self.coords)
        # advance to next pending city
        nxt = self._next_pending(self._current_idx)
        self._current_idx = nxt if nxt is not None else self._current_idx + 1
        if self._current_idx >= len(self.cities):
            self._current_idx = len(self.cities) - 1
        self._refresh_ui()

    def _next_pending(self, from_idx: int) -> int | None:
        for i in range(from_idx + 1, len(self.cities)):
            if self.cities[i]["key"] not in self.coords:
                return i
        for i in range(0, from_idx):
            if self.cities[i]["key"] not in self.coords:
                return i
        return None

    def _prev_city(self):
        self._current_idx = max(0, self._current_idx - 1)
        self._refresh_ui()

    def _next_city(self):
        self._current_idx = min(len(self.cities) - 1, self._current_idx + 1)
        self._refresh_ui()

    def _skip_city(self):
        c = self.cities[self._current_idx]
        self.coords.pop(c["key"], None)
        self.map_area.set_coords(self.coords)
        self._refresh_ui()

    def _save_and_quit(self):
        out = {k: [int(x), int(y)] for k, (x, y) in self.coords.items()}
        COORDS_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Saved {len(out)} city coords to {COORDS_PATH}")
        self.accept()


def main() -> int:
    if not CONFIG_PATH.exists():
        print(f"pr2_config.json not found at {CONFIG_PATH}", file=sys.stderr)
        return 1
    if not MAP_PATH.exists():
        print(f"Map image not found at {MAP_PATH}", file=sys.stderr)
        return 1

    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    cities = cfg["cities"]

    coords: dict[str, tuple[int, int]] = {}
    if COORDS_PATH.exists():
        raw = json.loads(COORDS_PATH.read_text(encoding="utf-8"))
        for k, v in raw.items():
            if isinstance(v, list) and len(v) == 2:
                coords[k] = (int(v[0]), int(v[1]))

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    pixmap = QtGui.QPixmap(str(MAP_PATH))
    if pixmap.isNull():
        print(f"Could not load map image {MAP_PATH}", file=sys.stderr)
        return 1

    dlg = CalibrationDialog(cities, coords, pixmap)
    code = dlg.exec()
    return 0 if code == QtWidgets.QDialog.Accepted else 0


if __name__ == "__main__":
    sys.exit(main())
