"""Map view: clickable map of the Caribbean with city markers + route drawing."""
from __future__ import annotations
import json
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from ..constants import (
    MAP_COORDS_PATH,
    MAP_IMAGE_PATH,
    NATION_LABELS,
    WAREHOUSE_TONS_PER_LEVEL,
)
from ..store import Store


CITY_MARKER_RADIUS = 9
CITY_MARKER_COLOR = QtGui.QColor(40, 90, 200, 200)
CITY_MARKER_HOVER = QtGui.QColor(255, 200, 40, 230)
CITY_MARKER_IN_ROUTE = QtGui.QColor(40, 180, 80, 220)
CITY_MARKER_START = QtGui.QColor(220, 60, 60, 230)
ROUTE_LINE_COLOR = QtGui.QColor(200, 80, 30, 220)
ROUTE_LINE_WIDTH = 3
BADGE_BG = QtGui.QColor(255, 255, 255, 230)
BADGE_BORDER = QtGui.QColor(40, 40, 40)


def load_map_coords() -> dict[str, tuple[int, int]]:
    """Return {city_key: (x, y)} loaded from pr2_map_coords.json, or {} if missing."""
    if not MAP_COORDS_PATH.exists():
        return {}
    raw = json.loads(MAP_COORDS_PATH.read_text(encoding="utf-8"))
    out: dict[str, tuple[int, int]] = {}
    for k, v in raw.items():
        if isinstance(v, list) and len(v) == 2:
            out[k] = (int(v[0]), int(v[1]))
    return out


class _CityMarker(QtWidgets.QGraphicsEllipseItem):
    """A clickable city marker on the map. Emits via the parent view's signals."""

    def __init__(self, city: dict, x: int, y: int, view: "MapView"):
        r = CITY_MARKER_RADIUS
        super().__init__(-r, -r, 2 * r, 2 * r)
        self.setPos(x, y)
        self.city = city
        self.view = view
        self._visit_orders: list[int] = []
        self.setBrush(QtGui.QBrush(CITY_MARKER_COLOR))
        self.setPen(QtGui.QPen(QtGui.QColor(20, 20, 20), 1.5))
        self.setAcceptHoverEvents(True)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setZValue(10)
        self._refresh_tooltip()

    def _refresh_tooltip(self) -> None:
        store = self.view.store
        c = self.city
        nation = store.city_nation(c["key"])
        nation_label = NATION_LABELS.get(nation, nation.capitalize())
        role = c.get("role") or "—"
        wlvl = store.city_warehouse_level(c["key"])
        wh = (f"<b>Warehouse:</b> level {wlvl} ({wlvl * WAREHOUSE_TONS_PER_LEVEL} t)"
              if wlvl > 0 else "<b>Warehouse:</b> no")
        prod_names = ", ".join(
            store.goods_by_id[g]["name_en"] for g in c.get("produces", []))
        if self._visit_orders:
            stops_str = ", ".join(f"#{o}" for o in self._visit_orders)
            action_hint = (
                f"<b>In route as stop {stops_str}.</b><br>"
                "<i>Right-click to remove · left-click to add another visit</i>"
            )
        else:
            action_hint = "<i>Left-click to add this city to the route</i>"
        html = (
            f"<h3 style='margin:0'>{c['name']}</h3>"
            f"<b>Nation:</b> {nation_label} &nbsp; "
            f"<b>Role:</b> {role}<br>"
            f"{wh}<br>"
            f"<b>Produces:</b> {prod_names or '—'}<br>"
            f"{action_hint}"
        )
        self.setToolTip(html)

    def set_route_state(self, in_route: bool, is_start: bool,
                        visit_orders: list[int] | None = None) -> None:
        self._visit_orders = list(visit_orders or [])
        if is_start:
            self.setBrush(QtGui.QBrush(CITY_MARKER_START))
        elif in_route:
            self.setBrush(QtGui.QBrush(CITY_MARKER_IN_ROUTE))
        else:
            self.setBrush(QtGui.QBrush(CITY_MARKER_COLOR))
        self._refresh_tooltip()

    def hoverEnterEvent(self, ev: QtWidgets.QGraphicsSceneHoverEvent) -> None:
        pen = self.pen()
        pen.setColor(QtGui.QColor(255, 200, 40))
        pen.setWidth(3)
        self.setPen(pen)
        super().hoverEnterEvent(ev)

    def hoverLeaveEvent(self, ev: QtWidgets.QGraphicsSceneHoverEvent) -> None:
        self.setPen(QtGui.QPen(QtGui.QColor(20, 20, 20), 1.5))
        super().hoverLeaveEvent(ev)

    def mousePressEvent(self, ev: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        if ev.button() == QtCore.Qt.LeftButton:
            self.view.city_clicked.emit(int(self.city["id"]))
            ev.accept()
            return
        if ev.button() == QtCore.Qt.RightButton:
            global_pos = ev.screenPos().toPoint() if hasattr(ev.screenPos(), "toPoint") else ev.screenPos()
            self.view.city_right_clicked.emit(int(self.city["id"]), global_pos)
            ev.accept()
            return
        super().mousePressEvent(ev)


class MapView(QtWidgets.QGraphicsView):
    """QGraphicsView showing the map, city markers, hover tooltip, and route lines."""

    city_clicked = QtCore.Signal(int)        # city_id (left-click)
    city_right_clicked = QtCore.Signal(int, QtCore.QPoint)  # city_id, global screen pos

    def __init__(self, store: Store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setRenderHint(QtGui.QPainter.Antialiasing, True)
        self.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)
        self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.setBackgroundBrush(QtGui.QColor(40, 50, 60))
        self._scene = QtWidgets.QGraphicsScene()
        self.setScene(self._scene)
        self._markers: dict[int, _CityMarker] = {}
        self._route_items: list[QtWidgets.QGraphicsItem] = []
        self._current_route_cids: list[int] = []
        self._zoom = 1.0
        self._build_scene()

    def _build_scene(self) -> None:
        pixmap = QtGui.QPixmap(str(MAP_IMAGE_PATH))
        if pixmap.isNull():
            placeholder = self._scene.addText("Map image not found.")
            placeholder.setDefaultTextColor(QtGui.QColor(220, 220, 220))
            return
        self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(0, 0, pixmap.width(), pixmap.height())

        coords = load_map_coords()
        missing: list[str] = []
        for c in self.store.config["cities"]:
            key = c["key"]
            if key not in coords:
                missing.append(c["name"])
                continue
            x, y = coords[key]
            marker = _CityMarker(c, x, y, self)
            self._scene.addItem(marker)
            self._markers[int(c["id"])] = marker

        if missing:
            n_total = len(self.store.config["cities"])
            n_done = n_total - len(missing)
            msg = (f"⚠ {len(missing)} cities missing coords ({n_done}/{n_total} placed). "
                   f"Run  python tools/calibrate_map.py  to add the rest.")
            # Background banner so the warning stands out over the map artwork
            font = QtGui.QFont()
            font.setBold(True)
            font.setPointSize(14)
            warn = QtWidgets.QGraphicsSimpleTextItem(msg)
            warn.setFont(font)
            warn.setBrush(QtGui.QColor(220, 30, 30))
            br = warn.boundingRect()
            bg = QtWidgets.QGraphicsRectItem(0, 0, br.width() + 24, br.height() + 16)
            bg.setBrush(QtGui.QBrush(QtGui.QColor(255, 240, 240, 240)))
            bg.setPen(QtGui.QPen(QtGui.QColor(180, 30, 30), 2))
            bg.setPos(20, 20)
            bg.setZValue(100)
            warn.setParentItem(bg)
            warn.setPos(12, 8)
            warn.setZValue(101)
            self._scene.addItem(bg)

    # --- route rendering ------------------------------------------------

    def set_route(self, city_ids_in_order: list[int]) -> None:
        """Update the rendered route. Lines connect stops in order; markers re-colored."""
        # Clear old route items
        for item in self._route_items:
            self._scene.removeItem(item)
        self._route_items = []
        self._current_route_cids = list(city_ids_in_order)

        # Marker colors + route-position bookkeeping
        visits: dict[int, list[int]] = {}
        for order_idx, cid in enumerate(city_ids_in_order, start=1):
            visits.setdefault(cid, []).append(order_idx)
        in_route = set(visits.keys())
        first_cid = city_ids_in_order[0] if city_ids_in_order else None
        for cid, marker in self._markers.items():
            marker.set_route_state(
                cid in in_route,
                is_start=(cid == first_cid),
                visit_orders=visits.get(cid, []),
            )

        # Lines connecting stops in order
        for i in range(len(city_ids_in_order) - 1):
            a = self._markers.get(city_ids_in_order[i])
            b = self._markers.get(city_ids_in_order[i + 1])
            if a is None or b is None:
                continue
            line = QtWidgets.QGraphicsLineItem(
                a.pos().x(), a.pos().y(), b.pos().x(), b.pos().y()
            )
            pen = QtGui.QPen(ROUTE_LINE_COLOR, ROUTE_LINE_WIDTH)
            pen.setCapStyle(QtCore.Qt.RoundCap)
            line.setPen(pen)
            line.setZValue(5)  # behind markers (z=10)
            self._scene.addItem(line)
            self._route_items.append(line)

        # One consolidated badge per city, listing every order index ("1,3" if visited twice)
        font = QtGui.QFont()
        font.setBold(True)
        font.setPointSize(9)
        for cid, orders in visits.items():
            marker = self._markers.get(cid)
            if marker is None:
                continue
            label = ",".join(str(o) for o in orders)
            text = QtWidgets.QGraphicsSimpleTextItem(label)
            text.setFont(font)
            br = text.boundingRect()
            w = max(20.0, br.width() + 10.0)
            h = 20.0
            cx = marker.pos().x() + 14
            cy = marker.pos().y() - 14
            badge = QtWidgets.QGraphicsEllipseItem(-w / 2, -h / 2, w, h)
            badge.setBrush(QtGui.QBrush(BADGE_BG))
            badge.setPen(QtGui.QPen(BADGE_BORDER, 1.2))
            badge.setPos(cx, cy)
            badge.setZValue(15)
            self._scene.addItem(badge)
            text.setPos(cx - br.width() / 2, cy - br.height() / 2)
            text.setZValue(16)
            self._scene.addItem(text)
            self._route_items.extend([badge, text])

    def refresh_tooltips(self) -> None:
        """Re-build tooltip text for every marker (call after user_state changes)."""
        for marker in self._markers.values():
            marker._refresh_tooltip()

    # --- zoom -----------------------------------------------------------

    def wheelEvent(self, ev: QtGui.QWheelEvent) -> None:
        # Ctrl + wheel = zoom; otherwise default scroll
        if ev.modifiers() & QtCore.Qt.ControlModifier:
            factor = 1.15 if ev.angleDelta().y() > 0 else 1.0 / 1.15
            self._zoom *= factor
            self._zoom = max(0.25, min(self._zoom, 4.0))
            self.resetTransform()
            self.scale(self._zoom, self._zoom)
            ev.accept()
            return
        super().wheelEvent(ev)

    def reset_zoom(self) -> None:
        self._zoom = 1.0
        self.resetTransform()

    def fit_to_view(self) -> None:
        rect = self._scene.sceneRect()
        if rect.isEmpty():
            return
        self.fitInView(rect, QtCore.Qt.KeepAspectRatio)
        self._zoom = self.transform().m11()
