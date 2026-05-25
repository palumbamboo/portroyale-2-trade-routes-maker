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
    NATION_LABELS,
    ROUTES_DIR,
    WAREHOUSE_PRICE,
    WAREHOUSE_TONS_PER_LEVEL,
)
from .icons import good_icon
from .route import Route
from .store import Store
from .style import apply_class_property
from .widgets.goods_table import GoodsTable
from .widgets.manage_cities_dialog import ManageCitiesDialog
from .widgets.map_view import MapView


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, store: Store):
        super().__init__()
        self.store = store
        self.route = Route(store)
        self._wire_route()
        self.store.user_state_changed.connect(self._on_user_state_changed)
        self.setWindowTitle(self._title())
        self.resize(1320, 820)
        self._build_menu()
        self._build_central()
        self._build_statusbar()
        self._on_route_changed()

    def _on_user_state_changed(self):
        idx = self._current_stop_idx()
        self._update_stop_panel(idx)
        self._refresh_table_for_stop(idx)
        self._refresh_status()
        self.map_view.refresh_tooltips()

    def _sync_map_view(self):
        cids = [s["trailer"]["city_id"] for s in self.route.stops]
        self.map_view.set_route(cids)

    def _on_show_map_view(self):
        self._sync_map_view()
        self.right_stack.setCurrentWidget(self.map_page)
        # Fit the map to the available area so the user never has to scroll on open.
        # Defer to the next event-loop tick so the widget has its post-show geometry.
        QtCore.QTimer.singleShot(0, self.map_view.fit_to_view)
        self.map_view.setFocus()

    def _exit_map_view(self):
        if self.right_stack.currentWidget() is self.map_page:
            self.right_stack.setCurrentWidget(self.goods_page)

    def _on_map_city_clicked(self, city_id: int):
        if len(self.route.stops) >= ahr.MAX_STOPS:
            QtWidgets.QMessageBox.warning(
                self, "Add stop", f"Maximum {ahr.MAX_STOPS} stops per route.")
            return
        try:
            idx = self.route.add_stop(int(city_id))
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", str(e))
            return
        self.stops_list.setCurrentRow(idx)

    def _on_map_city_right_clicked(self, city_id: int, global_pos: QtCore.QPoint):
        """Right-click on a map city: if it's in the route, offer to remove its stop(s)."""
        city = self.store.cities_by_id.get(int(city_id))
        name = city["name"] if city else f"city#{city_id}"
        matches = [i for i, s in enumerate(self.route.stops)
                   if int(s["trailer"]["city_id"]) == int(city_id)]
        if not matches:
            return
        menu = QtWidgets.QMenu(self)
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
        # "Edit route" is the accent primary action: it is the only way to add/remove stops
        btn_edit_route = QtWidgets.QPushButton("🗺  Edit route")
        btn_edit_route.setToolTip(
            "Open the map view: left-click a city to add a stop, "
            "right-click a stop to remove it. Drag rows above to reorder.")
        btn_edit_route.clicked.connect(self._on_show_map_view)
        apply_class_property(btn_edit_route, accent=True)
        lv.addWidget(btn_edit_route)
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

        # --- right: stacked area (goods page / map page) ---
        self.right_stack = QtWidgets.QStackedWidget()

        # === Goods page ===
        self.goods_page = QtWidgets.QWidget()
        gp_v = QtWidgets.QVBoxLayout(self.goods_page)
        gp_v.setSpacing(8)
        gp_v.setContentsMargins(0, 0, 0, 0)

        # Placeholder shown when no stop is selected
        self.goods_placeholder = QtWidgets.QLabel(
            "<div style='text-align:center'>"
            "<h2 style='color:#6b6b73; font-weight:500; margin-bottom:8px'>"
            "No stop selected</h2>"
            "<p style='color:#6b6b73; font-size:11pt'>"
            "Click <b>🗺 Edit route</b> on the left to add cities, "
            "then pick a stop from the list to edit its goods."
            "</p></div>")
        self.goods_placeholder.setTextFormat(QtCore.Qt.RichText)
        self.goods_placeholder.setAlignment(QtCore.Qt.AlignCenter)
        self.goods_placeholder.setWordWrap(True)
        gp_v.addWidget(self.goods_placeholder, 1)

        # Stop info card (hidden until a stop is selected)
        self.info_card = QtWidgets.QFrame()
        self.info_card.setObjectName("stopInfoCard")
        info_v = QtWidgets.QVBoxLayout(self.info_card)
        info_v.setContentsMargins(14, 10, 14, 10)
        info_v.setSpacing(2)
        self.stop_header = QtWidgets.QLabel("")
        self.stop_header.setStyleSheet("font-size: 15pt; font-weight: 600; color: #1f1f23;")
        self.stop_subtitle = QtWidgets.QLabel("")
        self.stop_subtitle.setStyleSheet("color: #4b5765; font-size: 10pt;")
        info_v.addWidget(self.stop_header)
        info_v.addWidget(self.stop_subtitle)
        gp_v.addWidget(self.info_card)

        self.goods_table = GoodsTable(self.store)
        self.goods_table.action_changed.connect(self._on_action_changed)
        self.goods_table.trade_changed.connect(self._on_trade_changed)
        self.goods_table.advised_price_requested.connect(self._on_advised_price_requested)
        self.goods_table.copy_good_requested.connect(self._on_copy_good)
        self.goods_table.paste_good_requested.connect(self._on_paste_good)
        self.goods_table.reset_good_requested.connect(self._on_reset_good)
        self._good_clipboard: dict | None = None
        self._stop_clipboard: dict | None = None
        gp_v.addWidget(self.goods_table, 1)

        # Info card and goods table start hidden; the placeholder takes the space
        self.info_card.setVisible(False)
        self.goods_table.setVisible(False)

        self.right_stack.addWidget(self.goods_page)

        # === Map page ===
        self.map_page = QtWidgets.QWidget()
        mp_v = QtWidgets.QVBoxLayout(self.map_page)
        mp_v.setContentsMargins(0, 0, 0, 0)
        mp_v.setSpacing(0)

        map_toolbar = QtWidgets.QFrame()
        map_toolbar.setStyleSheet("QFrame { background-color: #f3f3f5; border-bottom: 1px solid #d8d8dc; }")
        mt_h = QtWidgets.QHBoxLayout(map_toolbar)
        mt_h.setContentsMargins(10, 6, 10, 6)
        mt_h.setSpacing(8)

        btn_exit_map = QtWidgets.QPushButton("✖  Exit edit route  (Esc)")
        apply_class_property(btn_exit_map, accent=True)
        btn_exit_map.setToolTip("Return to goods editing")
        btn_exit_map.clicked.connect(self._exit_map_view)
        mt_h.addWidget(btn_exit_map)

        btn_fit_map = QtWidgets.QToolButton()
        btn_fit_map.setText("Fit window")
        btn_fit_map.clicked.connect(lambda: self.map_view.fit_to_view())
        mt_h.addWidget(btn_fit_map)

        btn_reset_zoom = QtWidgets.QToolButton()
        btn_reset_zoom.setText("Reset zoom")
        btn_reset_zoom.clicked.connect(lambda: self.map_view.reset_zoom())
        mt_h.addWidget(btn_reset_zoom)

        map_hint = QtWidgets.QLabel(
            "<i>Left-click a city to add a stop · right-click to remove · "
            "Ctrl + scroll to zoom · drag to pan</i>")
        map_hint.setTextFormat(QtCore.Qt.RichText)
        map_hint.setStyleSheet("color: #4b5765;")
        mt_h.addWidget(map_hint)
        mt_h.addStretch(1)
        mp_v.addWidget(map_toolbar)

        self.map_view = MapView(self.store)
        self.map_view.city_clicked.connect(self._on_map_city_clicked)
        self.map_view.city_right_clicked.connect(self._on_map_city_right_clicked)
        mp_v.addWidget(self.map_view, 1)

        # Esc shortcut to leave the map page
        self._sc_exit_map = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Escape), self.map_page)
        self._sc_exit_map.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
        self._sc_exit_map.activated.connect(self._exit_map_view)

        self.right_stack.addWidget(self.map_page)
        self.right_stack.setCurrentWidget(self.goods_page)

        splitter.addWidget(left); splitter.addWidget(self.right_stack)
        splitter.setStretchFactor(0, 1); splitter.setStretchFactor(1, 5)
        splitter.setSizes([240, 1080])
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
        self._sync_map_view()

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
        # Show placeholder when nothing is selected; show goods UI only when a stop is picked
        has_selection = idx is not None
        self.goods_placeholder.setVisible(not has_selection)
        self.info_card.setVisible(has_selection)
        self.goods_table.setVisible(has_selection)
        if idx is None:
            self.stop_header.setText("")
            self.stop_subtitle.setText("")
            return
        stop = self.route.stops[idx]
        cid = stop["trailer"]["city_id"]
        city = self.store.cities_by_id.get(cid)
        if not city:
            self.stop_header.setText(f"city#{cid} (unknown)")
            self.stop_subtitle.setText("")
            return
        is_start = bool(stop["trailer"]["start_flag"])
        self.stop_header.setText(
            f"{idx + 1}. {city['name']}" + ("  ★" if is_start else "")
        )
        nation = self.store.city_nation(city["key"])
        nation_label = NATION_LABELS.get(nation, nation.capitalize())
        role = city.get("role")
        role_label = {"V": "Capital", "G": "Governorate"}.get(role, "Regular")
        wlvl = self.store.city_warehouse_level(city["key"])
        if wlvl > 0:
            wh_label = f"Warehouse Lv{wlvl} ({wlvl * WAREHOUSE_TONS_PER_LEVEL} t)"
        else:
            wh_label = "No warehouse"
        start_label = " · Starting stop" if is_start else ""
        self.stop_subtitle.setText(
            f"{nation_label}  ·  {role_label}  ·  {wh_label}{start_label}"
        )

    # --- signals from the goods table ----------------------------------

    def _propagation_targets(self, good_id: int, *, manual_only: bool, stop: dict | None = None) -> list[int]:
        """Return the goods the edit should apply to.

        With ≥2 goods selected and the edited row in that selection, the change
        propagates to all selected goods (manual-only for trade/price changes).
        Otherwise it stays scoped to the row that was actually touched.
        """
        selected = self.goods_table.selected_gids
        if good_id in selected and len(selected) > 1:
            targets = sorted(selected)
        else:
            targets = [good_id]
        if manual_only and stop is not None:
            from .constants import ACTION_MANUAL as _M
            targets = [g for g in targets if stop["actions"][g] == _M]
        return targets

    def _on_action_changed(self, good_id: int, new_action: int):
        idx = self._current_stop_idx()
        if idx is None:
            return
        targets = self._propagation_targets(good_id, manual_only=False)
        for gid in targets:
            self.route.set_good_action(idx, gid, new_action)
        if len(targets) > 1:
            self.statusBar().showMessage(
                f"Action applied to {len(targets)} selected goods", 2500)

    def _on_trade_changed(self, good_id: int, side: str, mode: str, qty: int, price: int):
        idx = self._current_stop_idx()
        if idx is None:
            return
        stop = self.route.stops[idx]
        targets = self._propagation_targets(good_id, manual_only=True, stop=stop)
        for gid in targets:
            self.route.set_good_trade(idx, gid, side=side, mode=mode, qty=qty, price=price)
        if len(targets) > 1:
            self.statusBar().showMessage(
                f"{side.capitalize()} change applied to {len(targets)} selected manual goods", 2500)

    def _on_advised_price_requested(self, good_id: int, sides: str, scope: str):
        """Apply the recommended buy/sell price.

        - Without multi-select: scope = single row (Ctrl click = both sides, else just one).
        - With ≥2 selected and the clicked row in selection: apply to every selected manual good.
        """
        idx = self._current_stop_idx()
        if idx is None:
            return
        stop = self.route.stops[idx]
        city_key = self.store.cities_by_id[stop["trailer"]["city_id"]]["key"]
        targets = self._propagation_targets(good_id, manual_only=True, stop=stop)
        if not targets:
            return
        sides_to_apply = ["load", "unload"] if sides == "both" else [sides]
        applied, skipped = 0, 0
        for gid in targets:
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
            scope_lbl = f"{len(targets)} selected" if len(targets) > 1 else "1 good"
            side_lbl = "load+unload" if sides == "both" else ("load" if sides == "load" else "unload")
            self.statusBar().showMessage(
                f"Recommended price applied to {scope_lbl} ({side_lbl}): {applied} values updated"
                + (f" ({skipped} with no recommended)" if skipped else ""),
                4000,
            )

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
