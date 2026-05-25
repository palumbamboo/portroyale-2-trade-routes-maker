"""GoodsTable: editable inline table for the 20 goods of a stop, grouped in 5 sections.

Workflow:
- Each row exposes Action / Mode / Qty slider / Price slider / 💰 advised-price button
  for both Load and Unload.
- The icon column hosts a checkbox: ticking it adds the good to the multi-selection.
- A toolbar above the table provides a filter input and "Select all visible" /
  "Clear" buttons; whenever 2+ goods are selected, any edit on one auto-propagates
  to the others (handled by MainWindow).
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ..constants import (
    ACTION_AUTO,
    ACTION_EXCLUDED,
    ACTION_LABEL,
    ACTION_MANUAL,
    GOOD_SECTIONS,
    MODE_LABEL,
)
from ..icons import good_icon
from ..store import Store
from ..style import TINT_ROUTE_EXCLUDED, TINT_STOP_EXCLUDED
from .row_widgets import PriceSlider, QtySlider, _ModifierToolButton

PRICE_SLIDER_FALLBACK_MAX = 500  # used if a good has no price_max in config


class _NoWheelComboBox(QtWidgets.QComboBox):
    """ComboBox that ignores wheel events (so scrolling the table doesn't change values)."""

    def wheelEvent(self, ev: QtGui.QWheelEvent) -> None:
        ev.ignore()


def _row_for_gid(gid: int) -> int:
    """Map good_id (0..19) to its row index (header rows are 0,5,10,15,20)."""
    return 1 + (gid // 4) * 5 + (gid % 4)


def _gid_for_row(row: int) -> int | None:
    """Return the good_id for a row, or None if the row is a section header."""
    if row < 0 or row >= 25 or row % 5 == 0:
        return None
    return (row // 5) * 4 + (row % 5 - 1)


class _SectionTitleWidget(QtWidgets.QFrame):
    """Simple section header: a card with just the section title (no inline controls).

    Multi-select + auto-propagation supersedes the previous popover with per-section
    actions, so this widget is purely a visual separator.
    """

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("sectionHeader")
        h = QtWidgets.QHBoxLayout(self)
        h.setContentsMargins(10, 4, 10, 4)
        h.setSpacing(8)
        lbl = QtWidgets.QLabel(f"<b>{title}</b>")
        lbl.setTextFormat(QtCore.Qt.RichText)
        h.addWidget(lbl)
        h.addStretch(1)


class GoodsTable(QtWidgets.QWidget):
    """Inline table with all 20 goods editable, grouped in 5 sections + multi-select bar."""

    # Existing signals (MainWindow auto-propagates when ≥2 are selected)
    advised_price_requested = QtCore.Signal(int, str, str)
    action_changed = QtCore.Signal(int, int)
    trade_changed = QtCore.Signal(int, str, str, int, int)

    copy_good_requested = QtCore.Signal(int)
    paste_good_requested = QtCore.Signal(int)
    reset_good_requested = QtCore.Signal(int)

    # Emitted whenever the multi-selection size changes
    selection_changed = QtCore.Signal(int)  # number selected

    COL_ICON = 0
    COL_NAME = 1
    COL_ACTION = 2
    COL_L_MODE = 3
    COL_L_QTY = 4
    COL_L_PRICE = 5
    COL_L_ADV = 6
    COL_U_MODE = 7
    COL_U_QTY = 8
    COL_U_PRICE = 9
    COL_U_ADV = 10
    N_COLS = 11

    N_ROWS = 25  # 5 headers + 20 goods

    def __init__(self, store: Store, parent=None):
        super().__init__(parent)
        self.store = store
        self._stop: dict | None = None
        self._route_excluded: list[int] = []
        self._city_has_warehouse = False
        self._city_key: str | None = None
        self._city_produces: set[int] = set()
        self._suppress = False
        self._row_widgets: list[dict] = [{} for _ in range(20)]
        self._select_checkboxes: list[QtWidgets.QCheckBox] = [None] * 20  # type: ignore
        self._selected_gids: set[int] = set()
        self._build()

    @property
    def selected_gids(self) -> set[int]:
        return set(self._selected_gids)

    def _build(self):
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        # Toolbar: filter input + Select all + Clear + count label
        toolbar = QtWidgets.QFrame()
        toolbar.setObjectName("tableToolbar")
        tb_layout = QtWidgets.QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(0, 0, 0, 0)
        tb_layout.setSpacing(8)

        self.ed_filter = QtWidgets.QLineEdit()
        self.ed_filter.setPlaceholderText("🔍  Filter goods by name…")
        self.ed_filter.setClearButtonEnabled(True)
        self.ed_filter.setMaximumWidth(280)
        self.ed_filter.textChanged.connect(self._apply_filter)
        tb_layout.addWidget(self.ed_filter)

        self.btn_select_all = QtWidgets.QPushButton("Select all visible")
        self.btn_select_all.setToolTip(
            "Tick the checkbox of every visible good. With ≥2 selected, "
            "editing one row auto-propagates the change to the others.")
        self.btn_select_all.clicked.connect(self._select_all_visible)
        tb_layout.addWidget(self.btn_select_all)

        self.btn_clear_selection = QtWidgets.QPushButton("Clear selection")
        self.btn_clear_selection.clicked.connect(self.clear_selection)
        self.btn_clear_selection.setEnabled(False)
        tb_layout.addWidget(self.btn_clear_selection)

        tb_layout.addStretch(1)

        self.lbl_selection_count = QtWidgets.QLabel("")
        self.lbl_selection_count.setStyleSheet("font-weight: 600; color: #0a559a;")
        tb_layout.addWidget(self.lbl_selection_count)

        v.addWidget(toolbar)

        self.table = QtWidgets.QTableWidget(self.N_ROWS, self.N_COLS)
        self.table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        self.table.setHorizontalHeaderLabels([
            "", "Good", "Action",
            "Load · Mode", "Load · Qty", "Load · €/t", "Load · 💰",
            "Unload · Mode", "Unload · Qty", "Unload · €/t", "Unload · 💰",
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.table.setIconSize(QtCore.QSize(24, 24))
        self.table.setShowGrid(True)
        self.table.setAlternatingRowColors(True)
        self.table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        h = self.table.horizontalHeader()
        h.setSectionResizeMode(self.COL_ICON, QtWidgets.QHeaderView.Interactive)
        for c in range(1, self.N_COLS):
            h.setSectionResizeMode(c, QtWidgets.QHeaderView.Interactive)
        # Tight column widths so the whole table fits a ~1000 px right pane.
        self.table.setColumnWidth(self.COL_ICON,    48)
        self.table.setColumnWidth(self.COL_NAME,    96)
        self.table.setColumnWidth(self.COL_ACTION,  86)
        self.table.setColumnWidth(self.COL_L_MODE,  72)
        self.table.setColumnWidth(self.COL_L_QTY,  124)
        self.table.setColumnWidth(self.COL_L_PRICE,124)
        self.table.setColumnWidth(self.COL_L_ADV,   56)
        self.table.setColumnWidth(self.COL_U_MODE,  72)
        self.table.setColumnWidth(self.COL_U_QTY,  124)
        self.table.setColumnWidth(self.COL_U_PRICE,124)
        self.table.setColumnWidth(self.COL_U_ADV,   56)

        # Build section headers + good rows
        for sec_idx, (title, gids) in enumerate(GOOD_SECTIONS):
            header_row = sec_idx * 5
            self.table.setSpan(header_row, 0, 1, self.N_COLS)
            self.table.setRowHeight(header_row, 30)
            section_w = _SectionTitleWidget(title)
            self.table.setCellWidget(header_row, 0, section_w)
            for gid in gids:
                self._build_good_row(gid)

        v.addWidget(self.table)
        self.setEnabled(False)
        self._update_selection_label()

    def _build_good_row(self, gid: int) -> None:
        row = _row_for_gid(gid)
        g = self.store.goods_by_id[gid]

        # Icon column: composite [checkbox] + [icon label]
        icon_w = QtWidgets.QWidget()
        ih = QtWidgets.QHBoxLayout(icon_w)
        ih.setContentsMargins(2, 0, 2, 0)
        ih.setSpacing(2)
        checkbox = QtWidgets.QCheckBox()
        checkbox.setToolTip(
            "Select this good. With 2+ selected, editing one row "
            "auto-applies the same change to the others.")
        checkbox.stateChanged.connect(
            lambda state, gid=gid: self._on_select_changed(gid, state))
        ih.addWidget(checkbox)
        icon_lbl = QtWidgets.QLabel()
        icon_lbl.setPixmap(good_icon(gid).pixmap(22, 22))
        ih.addWidget(icon_lbl)
        ih.addStretch(0)
        self.table.setCellWidget(row, self.COL_ICON, icon_w)
        self._select_checkboxes[gid] = checkbox

        it_name = QtWidgets.QTableWidgetItem(g["name_en"])
        it_name.setFlags(it_name.flags() & ~QtCore.Qt.ItemIsEditable)
        it_name.setData(QtCore.Qt.UserRole, gid)
        self.table.setItem(row, self.COL_NAME, it_name)

        cb_action = _NoWheelComboBox()
        for av in (ACTION_AUTO, ACTION_EXCLUDED, ACTION_MANUAL):
            cb_action.addItem(ACTION_LABEL[av], av)
        cb_action.currentIndexChanged.connect(
            lambda _i, gid=gid: self._on_action_combo(gid))
        self.table.setCellWidget(row, self.COL_ACTION, cb_action)

        row_w: dict = {"action": cb_action}
        for side, c_mode, c_qty, c_price, c_adv in (
            ("load",   self.COL_L_MODE, self.COL_L_QTY, self.COL_L_PRICE, self.COL_L_ADV),
            ("unload", self.COL_U_MODE, self.COL_U_QTY, self.COL_U_PRICE, self.COL_U_ADV),
        ):
            cb_mode = _NoWheelComboBox()
            cb_mode.addItem(MODE_LABEL["city"], "city")
            cb_mode.addItem(MODE_LABEL["warehouse"], "warehouse")
            cb_mode.currentIndexChanged.connect(
                lambda _i, gid=gid, side=side: self._emit_trade(gid, side))
            self.table.setCellWidget(row, c_mode, cb_mode)

            qty_w = QtySlider()
            qty_w.valueChanged.connect(
                lambda _v, gid=gid, side=side: self._emit_trade(gid, side))
            self.table.setCellWidget(row, c_qty, qty_w)

            price_w = PriceSlider()
            p_min = int(g.get("price_min") or 0)
            p_max = int(g.get("price_max") or PRICE_SLIDER_FALLBACK_MAX)
            price_w.set_slider_range(p_min, p_max)
            price_w.valueChanged.connect(
                lambda _v, gid=gid, side=side: self._emit_trade(gid, side))
            price_w.spin.customContextMenuRequested.connect(
                lambda pos, gid=gid, side=side, sp=price_w.spin:
                    self._show_price_menu(sp, pos, gid, side))
            self.table.setCellWidget(row, c_price, price_w)

            btn_adv = _ModifierToolButton()
            btn_adv.setText("💰")
            btn_adv.setToolTipDuration(0)
            btn_adv.setMinimumWidth(44)
            btn_adv.clicked_with_mods.connect(
                lambda mods, gid=gid, side=side: self._on_adv_button(gid, side, mods))
            self.table.setCellWidget(row, c_adv, btn_adv)

            row_w[f"{side}_mode"]  = cb_mode
            row_w[f"{side}_qty"]   = qty_w
            row_w[f"{side}_price"] = price_w
            row_w[f"{side}_adv"]   = btn_adv

        self._row_widgets[gid] = row_w
        self.table.setRowHeight(row, 34)

    # --- public API ---------------------------------------------------

    def set_context(self, stop: dict | None, route_excluded: list[int],
                    city_key: str | None, city_has_warehouse: bool):
        self._stop = stop
        self._route_excluded = list(route_excluded or [])
        self._city_has_warehouse = city_has_warehouse
        self._city_key = city_key
        if city_key and city_key in self.store.cities_by_key:
            self._city_produces = set(self.store.cities_by_key[city_key].get("produces", []))
        else:
            self._city_produces = set()
        self.setEnabled(stop is not None)
        self._refresh()

    def clear_selection(self) -> None:
        self._suppress = True
        try:
            for cb in self._select_checkboxes:
                if cb is not None:
                    cb.setChecked(False)
        finally:
            self._suppress = False
        self._selected_gids.clear()
        self._update_selection_label()

    def _select_all_visible(self) -> None:
        """Tick every checkbox of currently visible rows (respects the filter)."""
        self._suppress = True
        added = 0
        try:
            for gid in range(20):
                row = _row_for_gid(gid)
                if self.table.isRowHidden(row):
                    continue
                cb = self._select_checkboxes[gid]
                if cb is not None and not cb.isChecked():
                    cb.setChecked(True)
                    added += 1
                self._selected_gids.add(gid)
        finally:
            self._suppress = False
        self._update_selection_label()

    def _apply_filter(self, text: str) -> None:
        q = text.lower().strip()
        for gid in range(20):
            row = _row_for_gid(gid)
            name = self.store.goods_by_id[gid]["name_en"].lower()
            self.table.setRowHidden(row, q != "" and q not in name)

    def _refresh(self):
        self._suppress = True
        try:
            if self._stop is None:
                for gid in range(20):
                    w = self._row_widgets[gid]
                    w["action"].setCurrentIndex(w["action"].findData(ACTION_AUTO))
                    for side in ("load", "unload"):
                        w[f"{side}_mode"].setCurrentIndex(0)
                        w[f"{side}_qty"].setValue(0)
                        w[f"{side}_price"].setValue(0)
                        w[f"{side}_adv"].setText("💰")
                        w[f"{side}_adv"].setEnabled(False)
                        self._set_side_enabled(gid, side, False)
                    self._set_row_visual(gid, False, False, False)
                return
            stop = self._stop
            for gid in range(20):
                w = self._row_widgets[gid]
                action = stop["actions"][gid]
                w["action"].setCurrentIndex(w["action"].findData(action))
                manual = (action == ACTION_MANUAL)
                route_excluded = gid in self._route_excluded
                stop_excluded = (action == ACTION_EXCLUDED)
                produced = gid in self._city_produces
                self._set_row_visual(gid, route_excluded, stop_excluded, produced)
                t = stop["trades"][gid]
                for side in ("load", "unload"):
                    mode = t[f"{side}_mode"]
                    qty = t[f"{side}_qty"]
                    price = t[f"{side}_price"]
                    cb = w[f"{side}_mode"]
                    cb.setCurrentIndex(cb.findData(mode))
                    w[f"{side}_qty"].setValue(qty)
                    if mode == "warehouse":
                        w[f"{side}_price"].setValue(0)
                        w[f"{side}_price"].setEnabled(False)
                    else:
                        w[f"{side}_price"].setEnabled(manual)
                        w[f"{side}_price"].setValue(min(price, 999_999))
                    self._set_side_enabled(gid, side, manual)
                    if self._city_key:
                        adv = self.store.city_advised_price(
                            self._city_key, gid,
                            "buy" if side == "load" else "sell"
                        )
                        ov = self.store.user_state["city_overrides"].get(
                            self._city_key, {}
                        ).get("advised_prices", {}).get(str(gid), {})
                        is_override = (("buy" if side == "load" else "sell") in ov)
                    else:
                        good = self.store.goods_by_id[gid]
                        adv = good.get("price_buy_advised" if side == "load" else "price_sell_advised", 0)
                        is_override = False
                    btn = w[f"{side}_adv"]
                    star = "*" if is_override else ""
                    if adv > 0:
                        btn.setText(f"💰{star}")
                        btn.setEnabled(manual)
                    else:
                        btn.setText("💰")
                        btn.setEnabled(False)
                    btn.setToolTip(self._adv_tooltip(side, adv, is_override))
        finally:
            self._suppress = False

    def _adv_tooltip(self, side: str, adv: int, override: bool) -> str:
        label = "buy" if side == "load" else "sell"
        if adv <= 0:
            return f"No recommended {label} price set."
        src = " (city override)" if override else ""
        return (
            f"Recommended {label} price: <b>{adv}</b>{src}<br>"
            f"<i>Click</i>: apply to this good, {label} side<br>"
            f"<i>Ctrl+Click</i>: apply to load+unload of this good<br>"
            f"<i>(With 2+ selected, the price applies to every selected good.)</i>"
        )

    def _set_side_enabled(self, gid: int, side: str, enabled: bool):
        w = self._row_widgets[gid]
        w[f"{side}_mode"].setEnabled(enabled)
        w[f"{side}_qty"].setEnabled(enabled)

    def _set_row_visual(self, gid: int, route_excluded: bool, stop_excluded: bool,
                        produced: bool):
        """Visual style for a good row: row tint + name styling + produced marker."""
        row = _row_for_gid(gid)
        name_item = self.table.item(row, self.COL_NAME)
        if not name_item:
            return
        base_name = self.store.goods_by_id[gid]["name_en"]
        prefix = "🟢 " if produced else ""
        name_item.setText(prefix + base_name)
        font = name_item.font()
        font.setStrikeOut(False)
        font.setItalic(False)
        tooltip_parts: list[str] = []
        if produced:
            tooltip_parts.append("Produced by this city")
        if route_excluded:
            font.setStrikeOut(True)
            name_item.setForeground(QtGui.QBrush(QtGui.QColor(180, 50, 50)))
            tint = TINT_ROUTE_EXCLUDED
            tooltip_parts.append("Excluded by route (global exclusion list)")
        elif stop_excluded:
            font.setItalic(True)
            name_item.setForeground(QtGui.QBrush(QtGui.QColor(140, 140, 140)))
            tint = TINT_STOP_EXCLUDED
            tooltip_parts.append("Excluded at this stop")
        else:
            name_item.setData(QtCore.Qt.ForegroundRole, None)
            tint = None
        name_item.setFont(font)
        name_item.setToolTip(" • ".join(tooltip_parts))

        if tint:
            name_item.setBackground(QtGui.QBrush(QtGui.QColor(tint)))
        else:
            name_item.setBackground(QtGui.QBrush())

        sheet = f"background-color: {tint};" if tint else ""
        for col in range(self.N_COLS):
            w = self.table.cellWidget(row, col)
            if w is not None:
                w.setStyleSheet(sheet)

    # --- selection ----------------------------------------------------

    def _on_select_changed(self, gid: int, _state) -> None:
        if self._suppress:
            return
        cb = self._select_checkboxes[gid]
        if cb is not None and cb.isChecked():
            self._selected_gids.add(gid)
        else:
            self._selected_gids.discard(gid)
        self._update_selection_label()

    def _update_selection_label(self) -> None:
        n = len(self._selected_gids)
        self.btn_clear_selection.setEnabled(n > 0)
        if n == 0:
            self.lbl_selection_count.setText("")
        else:
            self.lbl_selection_count.setText(
                f"{n} selected — editing one will apply to all"
            )
        self.selection_changed.emit(n)

    # --- internal signal handlers -------------------------------------

    def _on_action_combo(self, good_id: int):
        if self._suppress:
            return
        cb = self._row_widgets[good_id]["action"]
        new_action = cb.currentData()
        self.action_changed.emit(good_id, new_action)

    def _emit_trade(self, good_id: int, side: str):
        if self._suppress or self._stop is None:
            return
        if self._stop["actions"][good_id] != ACTION_MANUAL:
            return
        w = self._row_widgets[good_id]
        mode = w[f"{side}_mode"].currentData()
        qty = w[f"{side}_qty"].value()
        price = w[f"{side}_price"].value()
        self.trade_changed.emit(good_id, side, mode, qty, price)

    def _on_adv_button(self, good_id: int, side: str, mods: QtCore.Qt.KeyboardModifiers):
        if self._stop is None:
            return
        if self._stop["actions"][good_id] != ACTION_MANUAL:
            return
        ctrl = bool(mods & QtCore.Qt.ControlModifier)
        sides = "both" if ctrl else side
        # scope is now driven by the multi-selection, not by Shift.
        self.advised_price_requested.emit(good_id, sides, "selection_aware")

    def _on_context_menu(self, pos: QtCore.QPoint):
        if self._stop is None:
            return
        row = self.table.rowAt(pos.y())
        gid = _gid_for_row(row)
        if gid is None:
            return
        gname = self.store.goods_by_id[gid]["name_en"]
        menu = QtWidgets.QMenu(self)
        a_copy = menu.addAction(f"Copy config of '{gname}'")
        a_paste = menu.addAction(f"Paste config onto '{gname}'")
        menu.addSeparator()
        a_reset = menu.addAction(f"Reset '{gname}' to Auto")
        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen == a_copy:
            self.copy_good_requested.emit(gid)
        elif chosen == a_paste:
            self.paste_good_requested.emit(gid)
        elif chosen == a_reset:
            self.reset_good_requested.emit(gid)

    def _show_price_menu(self, sp: QtWidgets.QSpinBox, pos: QtCore.QPoint,
                         good_id: int, side: str):
        if self._stop is None or self._stop["actions"][good_id] != ACTION_MANUAL:
            return
        g = self.store.goods_by_id[good_id]
        menu = QtWidgets.QMenu(self)
        for label, value in [
            (f"Min: {g['price_min']}", g['price_min']),
            (f"Market: {g['price_market']}", g['price_market']),
            (f"Max: {g['price_max']}", g['price_max']),
        ]:
            if value <= 0:
                continue
            act = menu.addAction(label)
            act.triggered.connect(lambda _, v=value: (sp.setValue(v), self._emit_trade(good_id, side)))
        if menu.actions():
            menu.exec(sp.mapToGlobal(pos))
