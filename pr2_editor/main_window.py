"""MainWindow: main editor window."""
from __future__ import annotations
import copy
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

import ahr

from . import APP_NAME, __version__
from .constants import (
    ACTION_AUTO,
    ACTION_MANUAL,
    GOOD_SECTIONS,
    NATION_LABELS,
    ROUTES_DIR,
    WAREHOUSE_PRICE,
    WAREHOUSE_TONS_PER_LEVEL,
)
from .icons import good_icon
from .route import Route
from .store import Store
from .widgets.goods_table import GoodsTable
from .widgets.manage_cities_dialog import ManageCitiesDialog
from .widgets.map_window import MapWindow


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, store: Store):
        super().__init__()
        self.store = store
        self.route = Route(store)
        self._wire_route()
        self.store.user_state_changed.connect(self._on_user_state_changed)
        self.setWindowTitle(self._title())
        self.resize(1380, 820)
        self._map_window: MapWindow | None = None
        self._build_menu()
        self._build_central()
        self._build_statusbar()
        self._on_route_changed()

    def _on_user_state_changed(self):
        idx = self._current_stop_idx()
        self._update_stop_panel(idx)
        self._refresh_table_for_stop(idx)
        self._refresh_status()
        if self._map_window is not None:
            self._map_window.refresh_tooltips()

    def _sync_map_window(self):
        if self._map_window is None:
            return
        cids = [s["trailer"]["city_id"] for s in self.route.stops]
        self._map_window.set_route(cids)

    def _on_show_map_view(self):
        if self._map_window is None:
            self._map_window = MapWindow(self.store, parent=self)
            self._map_window.city_clicked.connect(self._on_map_city_clicked)
            self._map_window.city_right_clicked.connect(self._on_map_city_right_clicked)
            self._map_window.setAttribute(QtCore.Qt.WA_DeleteOnClose, False)
        self._sync_map_window()
        self._map_window.show()
        self._map_window.raise_()
        self._map_window.activateWindow()

    def _on_map_city_clicked(self, city_id: int):
        if len(self.route.stops) >= ahr.MAX_STOPS:
            QtWidgets.QMessageBox.warning(
                self._map_window or self, "Add stop",
                f"Maximum {ahr.MAX_STOPS} stops per route.")
            return
        try:
            idx = self.route.add_stop(int(city_id))
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self._map_window or self, "Error", str(e))
            return
        self.stops_list.setCurrentRow(idx)

    def _on_map_city_right_clicked(self, city_id: int, global_pos: QtCore.QPoint):
        """Right-click on a map city: if it's in the route, offer to remove its stop(s)."""
        city = self.store.cities_by_id.get(int(city_id))
        name = city["name"] if city else f"city#{city_id}"
        # Find every stop matching this city (a city can appear more than once in a route)
        matches = [i for i, s in enumerate(self.route.stops)
                   if int(s["trailer"]["city_id"]) == int(city_id)]
        if not matches:
            return  # nothing to remove for this city
        menu = QtWidgets.QMenu(self._map_window or self)
        actions: list[tuple[QtGui.QAction, int]] = []
        if len(matches) == 1:
            a = menu.addAction(f"Remove stop '{name}'")
            actions.append((a, matches[0]))
        else:
            for i in matches:
                a = menu.addAction(f"Remove stop {i + 1}: '{name}'")
                actions.append((a, i))
        chosen = menu.exec(global_pos)
        for a, i in actions:
            if chosen is a:
                self.route.remove_stop(i)
                return

    def _wire_route(self):
        self.route.changed.connect(self._on_route_changed)
        self.route.stop_changed.connect(self._on_stop_internally_changed)

    def _title(self) -> str:
        return f"{APP_NAME} — {self.route.display_name()}"

    def _build_menu(self):
        mb = self.menuBar()
        m_file = mb.addMenu("&File")
        for label, key, slot in [
            ("New route", QtGui.QKeySequence.New, self._on_new_route),
            ("Open route...", QtGui.QKeySequence.Open, self._on_open_route),
        ]:
            a = m_file.addAction(label); a.setShortcut(key); a.triggered.connect(slot)
        m_file.addSeparator()
        a = m_file.addAction("Save"); a.setShortcut(QtGui.QKeySequence.Save); a.triggered.connect(self._on_save_route)
        a = m_file.addAction("Save as..."); a.setShortcut(QtGui.QKeySequence.SaveAs); a.triggered.connect(self._on_save_route_as)
        m_file.addSeparator()
        a = m_file.addAction("Quit"); a.setShortcut(QtGui.QKeySequence.Quit); a.triggered.connect(self.close)

        m_edit = mb.addMenu("&Edit")
        m_edit.addAction("Copy").setShortcut(QtGui.QKeySequence.Copy)
        m_edit.addAction("Paste").setShortcut(QtGui.QKeySequence.Paste)

        m_tools = mb.addMenu("&Tools")
        m_tools.addAction("Map view...").triggered.connect(self._on_show_map_view)
        m_tools.addAction("Manage cities (warehouses, nations)...").triggered.connect(self._on_manage_cities)

        m_help = mb.addMenu("&Help")
        m_help.addAction("About").triggered.connect(self._on_about)

    def _build_central(self):
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        # --- left: stops + exclusions --------------
        left = QtWidgets.QWidget()
        lv = QtWidgets.QVBoxLayout(left)
        lv.addWidget(QtWidgets.QLabel("Route stops"))
        self.stops_list = QtWidgets.QListWidget()
        self.stops_list.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.stops_list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.stops_list.model().rowsMoved.connect(self._on_stops_reordered)
        self.stops_list.itemSelectionChanged.connect(self._on_stop_selected)
        self.stops_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.stops_list.customContextMenuRequested.connect(self._on_stop_context_menu)
        lv.addWidget(self.stops_list, 1)
        # Hint that the map is the way to add/remove stops
        hint_lbl = QtWidgets.QLabel(
            "<i>Use <b>Tools → Map view</b> to add (left-click) or remove "
            "(right-click) stops. Drag rows above to reorder.</i>")
        hint_lbl.setTextFormat(QtCore.Qt.RichText)
        hint_lbl.setWordWrap(True)
        lv.addWidget(hint_lbl)
        lv.addWidget(QtWidgets.QLabel("Global exclusions"))
        self.route_excl_list = QtWidgets.QListWidget()
        self.route_excl_list.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        for g in self.store.config["goods"]:
            it = QtWidgets.QListWidgetItem(good_icon(g["id"]), g["name_en"])
            it.setFlags(it.flags() | QtCore.Qt.ItemIsUserCheckable)
            it.setCheckState(QtCore.Qt.Unchecked)
            it.setData(QtCore.Qt.UserRole, g["id"])
            self.route_excl_list.addItem(it)
        self.route_excl_list.itemChanged.connect(self._on_route_excl_changed)
        lv.addWidget(self.route_excl_list, 1)

        # --- right: city header + goods table ----------
        right = QtWidgets.QWidget()
        rv = QtWidgets.QVBoxLayout(right)
        self.stop_header = QtWidgets.QLabel("(no stop selected)")
        self.stop_header.setStyleSheet("font-size:14pt; font-weight:bold;")
        rv.addWidget(self.stop_header)
        self.stop_meta = QtWidgets.QLabel("")
        self.stop_meta.setTextFormat(QtCore.Qt.RichText)
        self.stop_meta.setWordWrap(True)
        rv.addWidget(self.stop_meta)
        sep = QtWidgets.QFrame(); sep.setFrameShape(QtWidgets.QFrame.HLine); rv.addWidget(sep)
        hint = QtWidgets.QLabel(
            "<i>💰 recommended price &nbsp;•&nbsp; "
            "Click: only this good+side &nbsp;•&nbsp; "
            "Ctrl+Click: load+unload &nbsp;•&nbsp; "
            "Shift+Click: every manual good &nbsp;•&nbsp; "
            "right-click on price: choose Min/Market/Max</i>"
        )
        hint.setTextFormat(QtCore.Qt.RichText)
        hint.setWordWrap(True)
        rv.addWidget(hint)
        self.goods_table = GoodsTable(self.store)
        self.goods_table.action_changed.connect(self._on_action_changed)
        self.goods_table.trade_changed.connect(self._on_trade_changed)
        self.goods_table.advised_price_requested.connect(self._on_advised_price_requested)
        self.goods_table.copy_good_requested.connect(self._on_copy_good)
        self.goods_table.paste_good_requested.connect(self._on_paste_good)
        self.goods_table.reset_good_requested.connect(self._on_reset_good)
        self.goods_table.section_action_apply.connect(self._on_section_action_apply)
        self.goods_table.section_mode_apply.connect(self._on_section_mode_apply)
        self.goods_table.section_advised_apply.connect(self._on_section_advised_apply)
        self.goods_table.section_qty_apply.connect(self._on_section_qty_apply)
        self.goods_table.bulk_action_apply.connect(self._on_bulk_action_apply)
        self.goods_table.bulk_mode_apply.connect(self._on_bulk_mode_apply)
        self.goods_table.bulk_advised_apply.connect(self._on_bulk_advised_apply)
        self.goods_table.bulk_qty_apply.connect(self._on_bulk_qty_apply)
        self._good_clipboard: dict | None = None
        self._stop_clipboard: dict | None = None
        rv.addWidget(self.goods_table, 1)

        splitter.addWidget(left); splitter.addWidget(right)
        splitter.setStretchFactor(0, 1); splitter.setStretchFactor(1, 5)
        splitter.setSizes([240, 1100])
        self.setCentralWidget(splitter)

    def _build_statusbar(self):
        self.statusBar()
        self._refresh_status()

    def _refresh_status(self):
        ovs = len(self.store.user_state["city_overrides"])
        n = len(self.route.stops)
        excl = len(self.route.excluded_route)
        self.statusBar().showMessage(
            f"{self.route.display_name()} • {n}/{ahr.MAX_STOPS} stops • "
            f"{excl} goods excluded • user state: {ovs} overrides"
        )

    # --- helpers --------------------------------------------------------

    def _current_stop_idx(self) -> int | None:
        i = self.stops_list.currentRow()
        if 0 <= i < len(self.route.stops):
            return i
        return None

    # --- UI updates ----------------------------------------------------

    def _on_route_changed(self):
        sel_idx = self.stops_list.currentRow()
        was = self.stops_list.blockSignals(True)
        try:
            self.stops_list.clear()
            for i, s in enumerate(self.route.stops):
                cid = s["trailer"]["city_id"]
                city = self.store.cities_by_id.get(cid)
                name = city["name"] if city else f"city#{cid}"
                start = " ★" if s["trailer"]["start_flag"] else ""
                it = QtWidgets.QListWidgetItem(f"{i+1}. {name}{start}")
                it.setData(QtCore.Qt.UserRole, cid)
                self.stops_list.addItem(it)
        finally:
            self.stops_list.blockSignals(was)
        if 0 <= sel_idx < len(self.route.stops):
            self.stops_list.setCurrentRow(sel_idx)
        elif self.route.stops:
            self.stops_list.setCurrentRow(0)
        else:
            self._update_stop_panel(None)
            self.goods_table.set_context(None, [], None, False)

        was = self.route_excl_list.blockSignals(True)
        try:
            excl = set(self.route.excluded_route)
            for i in range(self.route_excl_list.count()):
                it = self.route_excl_list.item(i)
                gid = it.data(QtCore.Qt.UserRole)
                it.setCheckState(QtCore.Qt.Checked if gid in excl else QtCore.Qt.Unchecked)
        finally:
            self.route_excl_list.blockSignals(was)
        idx = self._current_stop_idx()
        if idx is not None:
            self._refresh_table_for_stop(idx)
        self.setWindowTitle(self._title())
        self._refresh_status()
        self._sync_map_window()

    def _on_stop_internally_changed(self, stop_idx: int):
        if stop_idx == self._current_stop_idx():
            self._refresh_table_for_stop(stop_idx)
        self.setWindowTitle(self._title())
        self._refresh_status()

    def _on_stop_selected(self):
        idx = self._current_stop_idx()
        self._update_stop_panel(idx)
        self._refresh_table_for_stop(idx)
        self.goods_table.clear_selection()

    def _refresh_table_for_stop(self, idx: int | None):
        if idx is None:
            self.goods_table.set_context(None, [], None, False)
            return
        stop = self.route.stops[idx]
        cid = stop["trailer"]["city_id"]
        city_key = self.store.cities_by_id[cid]["key"]
        has_wh = self.store.city_has_warehouse(city_key)
        self.goods_table.set_context(stop, self.route.excluded_route, city_key, has_wh)

    def _update_stop_panel(self, idx: int | None):
        if idx is None:
            self.stop_header.setText("(no stop selected)")
            self.stop_meta.setText("")
            return
        stop = self.route.stops[idx]
        cid = stop["trailer"]["city_id"]
        city = self.store.cities_by_id.get(cid)
        if not city:
            self.stop_header.setText(f"city#{cid} (unknown)")
            self.stop_meta.setText("")
            return
        is_start = bool(stop["trailer"]["start_flag"])
        self.stop_header.setText(f"{idx + 1}. {city['name']}" + (" ★ (start)" if is_start else ""))
        role = city.get("role") or "—"
        nation = self.store.city_nation(city["key"])
        nation_label = NATION_LABELS.get(nation, nation.capitalize())
        wlvl = self.store.city_warehouse_level(city["key"])
        wh = (f"level {wlvl} ({wlvl * WAREHOUSE_TONS_PER_LEVEL} t)" if wlvl > 0 else "no")
        prod_ids = city.get("produces", [])
        prod_names = ", ".join(self.store.goods_by_id[g]["name_en"] for g in prod_ids)
        self.stop_meta.setText(
            f"<b>city id:</b> {cid} &nbsp; "
            f"<b>current nation:</b> {nation_label} &nbsp; "
            f"<b>role:</b> {role} &nbsp; "
            f"<b>warehouse:</b> {wh}<br>"
            f"<b>produces:</b> {prod_names}"
        )

    # --- signals from the goods table ----------------------------------

    def _on_action_changed(self, good_id: int, new_action: int):
        idx = self._current_stop_idx()
        if idx is None:
            return
        self.route.set_good_action(idx, good_id, new_action)

    def _on_trade_changed(self, good_id: int, side: str, mode: str, qty: int, price: int):
        idx = self._current_stop_idx()
        if idx is None:
            return
        self.route.set_good_trade(idx, good_id, side=side, mode=mode, qty=qty, price=price)

    def _on_advised_price_requested(self, good_id: int, sides: str, scope: str):
        idx = self._current_stop_idx()
        if idx is None:
            return
        stop = self.route.stops[idx]
        city_key = self.store.cities_by_id[stop["trailer"]["city_id"]]["key"]
        if scope == "all":
            target_gids = [g for g in range(20) if stop["actions"][g] == ACTION_MANUAL]
        else:
            if stop["actions"][good_id] != ACTION_MANUAL:
                return
            target_gids = [good_id]
        sides_to_apply = ["load", "unload"] if sides == "both" else [sides]
        applied, skipped = 0, 0
        for gid in target_gids:
            for side in sides_to_apply:
                price_side = "buy" if side == "load" else "sell"
                adv = self.store.city_advised_price(city_key, gid, price_side)
                if adv <= 0:
                    skipped += 1
                    continue
                t = stop["trades"][gid]
                mode = t[f"{side}_mode"]; qty = t[f"{side}_qty"]
                if mode == "warehouse":
                    mode = "city"
                self.route.set_good_trade(idx, gid, side=side, mode=mode, qty=qty, price=adv)
                applied += 1
        if applied:
            scope_lbl = f"all ({len(target_gids)})" if scope == "all" else "1 good"
            side_lbl = "load+unload" if sides == "both" else ("load" if sides == "load" else "unload")
            self.statusBar().showMessage(
                f"Applied recommended price to {scope_lbl}, {side_lbl}: {applied} values updated"
                + (f" ({skipped} with no recommended)" if skipped else ""),
                4000,
            )

    # --- shared helpers for section / bulk actions ---------------------

    def _apply_action_to_gids(self, idx: int, gids: list[int], action: int) -> int:
        for gid in gids:
            self.route.set_good_action(idx, gid, action)
        return len(gids)

    def _apply_mode_to_gids(self, idx: int, gids: list[int], mode: str) -> int:
        stop = self.route.stops[idx]
        applied = 0
        for gid in gids:
            if stop["actions"][gid] != ACTION_MANUAL:
                continue
            for side in ("load", "unload"):
                t = stop["trades"][gid]
                qty = t[f"{side}_qty"]
                price_raw = t[f"{side}_price"]
                if mode == "warehouse":
                    price = 0
                else:
                    price = price_raw if price_raw != WAREHOUSE_PRICE else 0
                self.route.set_good_trade(idx, gid, side=side, mode=mode, qty=qty, price=price)
                applied += 1
        return applied

    def _apply_advised_to_gids(self, idx: int, gids: list[int]) -> tuple[int, int]:
        stop = self.route.stops[idx]
        city_key = self.store.cities_by_id[stop["trailer"]["city_id"]]["key"]
        applied, skipped = 0, 0
        for gid in gids:
            if stop["actions"][gid] != ACTION_MANUAL:
                continue
            for side in ("load", "unload"):
                price_side = "buy" if side == "load" else "sell"
                adv = self.store.city_advised_price(city_key, gid, price_side)
                if adv <= 0:
                    skipped += 1
                    continue
                t = stop["trades"][gid]
                qty = t[f"{side}_qty"]
                mode = t[f"{side}_mode"]
                if mode == "warehouse":
                    mode = "city"
                self.route.set_good_trade(idx, gid, side=side, mode=mode, qty=qty, price=adv)
                applied += 1
        return applied, skipped

    def _apply_qty_to_gids(self, idx: int, gids: list[int], qty: int) -> int:
        stop = self.route.stops[idx]
        applied = 0
        for gid in gids:
            if stop["actions"][gid] != ACTION_MANUAL:
                continue
            for side in ("load", "unload"):
                t = stop["trades"][gid]
                mode = t[f"{side}_mode"]
                price_raw = t[f"{side}_price"]
                if mode == "warehouse":
                    price = 0
                else:
                    price = price_raw if price_raw != WAREHOUSE_PRICE else 0
                self.route.set_good_trade(idx, gid, side=side, mode=mode, qty=qty, price=price)
                applied += 1
        return applied

    # --- section commands ----------------------------------------------

    def _on_section_action_apply(self, section_idx: int, action: int):
        idx = self._current_stop_idx()
        if idx is None:
            return
        title, gids = GOOD_SECTIONS[section_idx]
        n = self._apply_action_to_gids(idx, gids, action)
        self.statusBar().showMessage(
            f"Section '{title}': action applied to {n} goods", 3000)

    def _on_section_mode_apply(self, section_idx: int, mode: str):
        idx = self._current_stop_idx()
        if idx is None:
            return
        title, gids = GOOD_SECTIONS[section_idx]
        n = self._apply_mode_to_gids(idx, gids, mode)
        self.statusBar().showMessage(
            f"Section '{title}': mode '{mode}' applied to {n} values", 3000)

    def _on_section_advised_apply(self, section_idx: int):
        idx = self._current_stop_idx()
        if idx is None:
            return
        title, gids = GOOD_SECTIONS[section_idx]
        applied, skipped = self._apply_advised_to_gids(idx, gids)
        msg = f"Section '{title}': applied {applied} recommended prices"
        if skipped:
            msg += f" ({skipped} with no recommended)"
        self.statusBar().showMessage(msg, 4000)

    def _on_section_qty_apply(self, section_idx: int, qty: int):
        idx = self._current_stop_idx()
        if idx is None:
            return
        title, gids = GOOD_SECTIONS[section_idx]
        applied = self._apply_qty_to_gids(idx, gids, qty)
        self.statusBar().showMessage(
            f"Section '{title}': qty={qty} set on {applied} values", 3000)

    # --- bulk (multi-select) commands ----------------------------------

    def _on_bulk_action_apply(self, gids: list, action: int):
        idx = self._current_stop_idx()
        if idx is None:
            return
        n = self._apply_action_to_gids(idx, list(gids), int(action))
        self.statusBar().showMessage(
            f"Selection: action applied to {n} goods", 3000)

    def _on_bulk_mode_apply(self, gids: list, mode: str):
        idx = self._current_stop_idx()
        if idx is None:
            return
        n = self._apply_mode_to_gids(idx, list(gids), str(mode))
        self.statusBar().showMessage(
            f"Selection: mode '{mode}' applied to {n} values", 3000)

    def _on_bulk_advised_apply(self, gids: list):
        idx = self._current_stop_idx()
        if idx is None:
            return
        applied, skipped = self._apply_advised_to_gids(idx, list(gids))
        msg = f"Selection: applied {applied} recommended prices"
        if skipped:
            msg += f" ({skipped} with no recommended)"
        self.statusBar().showMessage(msg, 4000)

    def _on_bulk_qty_apply(self, gids: list, qty: int):
        idx = self._current_stop_idx()
        if idx is None:
            return
        applied = self._apply_qty_to_gids(idx, list(gids), int(qty))
        self.statusBar().showMessage(
            f"Selection: qty={qty} set on {applied} values", 3000)

    # --- copy/paste ----------------------------------------------------

    def _on_copy_good(self, good_id: int):
        idx = self._current_stop_idx()
        if idx is None:
            return
        stop = self.route.stops[idx]
        self._good_clipboard = {
            "action": stop["actions"][good_id],
            "trade": copy.deepcopy(stop["trades"][good_id]),
        }
        gname = self.store.goods_by_id[good_id]["name_en"]
        self.statusBar().showMessage(f"Copied '{gname}' to clipboard", 3000)

    def _on_paste_good(self, good_id: int):
        if not self._good_clipboard:
            QtWidgets.QMessageBox.information(self, "Paste", "No good config in clipboard.")
            return
        idx = self._current_stop_idx()
        if idx is None:
            return
        stop = self.route.stops[idx]
        src = self._good_clipboard
        self.route.set_good_action(idx, good_id, src["action"])
        if src["action"] == ACTION_MANUAL:
            for side in ("load", "unload"):
                mode = src["trade"][f"{side}_mode"]
                qty = src["trade"][f"{side}_qty"]
                price_raw = src["trade"][f"{side}_price"]
                if mode == "warehouse":
                    price = 0
                else:
                    price = price_raw if price_raw != WAREHOUSE_PRICE else 0
                self.route.set_good_trade(idx, good_id, side=side, mode=mode, qty=qty, price=price)
        gname = self.store.goods_by_id[good_id]["name_en"]
        self.statusBar().showMessage(f"Pasted config onto '{gname}'", 3000)

    def _on_reset_good(self, good_id: int):
        idx = self._current_stop_idx()
        if idx is None:
            return
        self.route.set_good_action(idx, good_id, ACTION_AUTO)

    def _on_stop_context_menu(self, pos: QtCore.QPoint):
        item = self.stops_list.itemAt(pos)
        if not item:
            return
        row = self.stops_list.row(item)
        if not (0 <= row < len(self.route.stops)):
            return
        city = self.store.cities_by_id.get(self.route.stops[row]["trailer"]["city_id"])
        name = city["name"] if city else f"#{row}"
        menu = QtWidgets.QMenu(self)
        a_copy = menu.addAction(f"Copy entire stop '{name}'")
        a_paste = menu.addAction(f"Paste config onto '{name}'")
        chosen = menu.exec(self.stops_list.viewport().mapToGlobal(pos))
        if chosen == a_copy:
            self._copy_stop(row)
        elif chosen == a_paste:
            self._paste_stop(row)

    def _copy_stop(self, idx: int):
        stop = self.route.stops[idx]
        self._stop_clipboard = {
            "display_order": list(stop["display_order"]),
            "actions": list(stop["actions"]),
            "trades": copy.deepcopy(stop["trades"]),
        }
        city = self.store.cities_by_id.get(stop["trailer"]["city_id"])
        name = city["name"] if city else "?"
        self.statusBar().showMessage(f"Copied entire stop '{name}' to clipboard", 3000)

    def _paste_stop(self, idx: int):
        if not self._stop_clipboard:
            QtWidgets.QMessageBox.information(self, "Paste", "No stop config in clipboard.")
            return
        if not (0 <= idx < len(self.route.stops)):
            return
        stop = self.route.stops[idx]
        src = self._stop_clipboard
        stop["display_order"] = list(src["display_order"])
        stop["actions"] = list(src["actions"])
        stop["trades"] = copy.deepcopy(src["trades"])
        stop["action_kinds"] = [ahr.ACTION_NAMES.get(a, "?") for a in stop["actions"]]
        self.route.set_dirty()
        self.route.stop_changed.emit(idx)
        city = self.store.cities_by_id.get(stop["trailer"]["city_id"])
        name = city["name"] if city else "?"
        self.statusBar().showMessage(f"Pasted config onto stop '{name}'", 3000)

    def _on_route_excl_changed(self, item: QtWidgets.QListWidgetItem):
        excl = []
        for i in range(self.route_excl_list.count()):
            it = self.route_excl_list.item(i)
            if it.checkState() == QtCore.Qt.Checked:
                excl.append(it.data(QtCore.Qt.UserRole))
        self.route.set_excluded_route(excl)

    def _on_stops_reordered(self, *args):
        new_ids = [self.stops_list.item(i).data(QtCore.Qt.UserRole) for i in range(self.stops_list.count())]
        if len(new_ids) != len(self.route.stops):
            return
        new_stops, used = [], set()
        for cid in new_ids:
            for j, s in enumerate(self.route.stops):
                if j in used:
                    continue
                if s["trailer"]["city_id"] == cid:
                    new_stops.append(s); used.add(j); break
        if len(new_stops) == len(self.route.stops):
            self.route.doc["stops"] = new_stops
            self.route._recompute_start_flags()
            self.route.set_dirty()
            self.route.changed.emit()

    # --- menu actions --------------------------------------------------

    def _maybe_discard_unsaved(self) -> bool:
        if not self.route.dirty:
            return True
        r = QtWidgets.QMessageBox.question(
            self, "Unsaved changes",
            "The current route has unsaved changes. Save first?",
            QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Cancel,
            QtWidgets.QMessageBox.Save,
        )
        if r == QtWidgets.QMessageBox.Save:
            return self._on_save_route()
        return r == QtWidgets.QMessageBox.Discard

    def _on_new_route(self):
        if not self._maybe_discard_unsaved():
            return
        self.route = Route(self.store); self._wire_route(); self._on_route_changed()

    def _on_open_route(self):
        if not self._maybe_discard_unsaved():
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open route", str(ROUTES_DIR), "AHR files (*.ahr)")
        if not path:
            return
        try:
            self.route = Route.from_file(self.store, Path(path)); self._wire_route()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Open error", f"{type(e).__name__}: {e}")
            return
        self._on_route_changed()

    def _on_save_route(self) -> bool:
        if not self.route.stops:
            QtWidgets.QMessageBox.warning(self, "Save", "Cannot save a route with no stops.")
            return False
        if not self.route.filepath:
            return self._on_save_route_as()
        try:
            self.route.save_to(self.route.filepath)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Save error", f"{type(e).__name__}: {e}")
            return False
        self._on_route_changed()
        return True

    def _on_save_route_as(self) -> bool:
        if not self.route.stops:
            QtWidgets.QMessageBox.warning(self, "Save as", "Cannot save a route with no stops.")
            return False
        default_dir = ROUTES_DIR / "built"; default_dir.mkdir(parents=True, exist_ok=True)
        suggested = str(default_dir / "route.ahr")
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save route as", suggested, "AHR files (*.ahr)")
        if not path:
            return False
        try:
            self.route.save_to(Path(path))
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Save error", f"{type(e).__name__}: {e}")
            return False
        self._on_route_changed()
        return True

    def _on_manage_cities(self):
        dlg = ManageCitiesDialog(self.store, self)
        dlg.exec()

    def _on_about(self):
        QtWidgets.QMessageBox.about(
            self, "About",
            f"<h3>{APP_NAME}</h3><p>Version {__version__}</p>"
            "<p>Editor for trade routes (.ahr) of Port Royale 2 — Empire & Pirates.</p>"
        )

    def closeEvent(self, ev: QtGui.QCloseEvent):
        if self._maybe_discard_unsaved():
            ev.accept()
        else:
            ev.ignore()
