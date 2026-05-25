"""GoodsTable: editable inline table for the 20 goods of a stop, grouped in 5 sections."""
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
from .row_widgets import PriceSlider, QtySlider, _ModifierToolButton

PRICE_SLIDER_FALLBACK_MAX = 500  # used if a good has no price_max in config


def _row_for_gid(gid: int) -> int:
    """Map good_id (0..19) to its row index (header rows are 0,5,10,15,20)."""
    return 1 + (gid // 4) * 5 + (gid % 4)


def _gid_for_row(row: int) -> int | None:
    """Return the good_id for a row, or None if the row is a section header."""
    if row < 0 or row >= 25 or row % 5 == 0:
        return None
    return (row // 5) * 4 + (row % 5 - 1)


class _SectionHeaderWidget(QtWidgets.QWidget):
    """Section header row with quick commands for the 4 goods in it."""

    # All signals carry the section index (0..4) as first argument.
    action_apply = QtCore.Signal(int, int)         # section_idx, action_value
    mode_apply = QtCore.Signal(int, str)           # section_idx, 'city'|'warehouse'
    advised_apply = QtCore.Signal(int)             # section_idx
    qty_apply = QtCore.Signal(int, int)            # section_idx, qty_value

    def __init__(self, section_idx: int, title: str, parent=None):
        super().__init__(parent)
        self.section_idx = section_idx
        self._has_warehouse = False
        self._build(title)

    def _build(self, title: str) -> None:
        h = QtWidgets.QHBoxLayout(self)
        h.setContentsMargins(8, 4, 8, 4)
        h.setSpacing(8)

        lbl = QtWidgets.QLabel(f"▾ <b>{title}</b>")
        lbl.setTextFormat(QtCore.Qt.RichText)
        lbl.setMinimumWidth(190)
        h.addWidget(lbl)

        # Action dropdown
        self.cb_action = QtWidgets.QComboBox()
        self.cb_action.addItem("Action…", None)
        self.cb_action.addItem(ACTION_LABEL[ACTION_AUTO], ACTION_AUTO)
        self.cb_action.addItem(ACTION_LABEL[ACTION_EXCLUDED], ACTION_EXCLUDED)
        self.cb_action.addItem(ACTION_LABEL[ACTION_MANUAL], ACTION_MANUAL)
        self.cb_action.setToolTip(
            "Apply the same action to all 4 goods in this section")
        self.cb_action.currentIndexChanged.connect(self._on_action_changed)
        h.addWidget(self.cb_action)

        # Mode dropdown (city / warehouse)
        self.cb_mode = QtWidgets.QComboBox()
        self.cb_mode.addItem("Mode…", None)
        self.cb_mode.addItem(f"All: {MODE_LABEL['city']}", "city")
        self.cb_mode.addItem(f"All: {MODE_LABEL['warehouse']}", "warehouse")
        self.cb_mode.setToolTip(
            "Apply the mode (load+unload) to every manual good in this section")
        self.cb_mode.currentIndexChanged.connect(self._on_mode_changed)
        h.addWidget(self.cb_mode)

        # Apply recommended prices button
        btn_adv = QtWidgets.QToolButton()
        btn_adv.setText("💰 Apply recommended prices")
        btn_adv.setToolTip(
            "Apply recommended buy/sell prices to every manual good in this section")
        btn_adv.clicked.connect(lambda: self.advised_apply.emit(self.section_idx))
        h.addWidget(btn_adv)

        # Qty input (same slider as row cells) + apply button — fixed width
        h.addSpacing(4)
        h.addWidget(QtWidgets.QLabel("Qty:"))
        self.qty_slider = QtySlider()
        self.qty_slider.setMinimumWidth(210)
        self.qty_slider.setMaximumWidth(240)
        self.qty_slider.setToolTip(
            "Drag (0–2000, end = MAX) or type a value. "
            "Press 'Apply' to set it on load+unload of every manual good in this section.")
        h.addWidget(self.qty_slider)
        btn_qty = QtWidgets.QToolButton()
        btn_qty.setText("Apply")
        btn_qty.setToolTip(
            "Set this quantity on load+unload of every manual good in this section")
        btn_qty.clicked.connect(lambda: self.qty_apply.emit(self.section_idx, self.qty_slider.value()))
        h.addWidget(btn_qty)

        h.addStretch(1)

    def set_has_warehouse(self, has_wh: bool) -> None:
        self._has_warehouse = has_wh
        idx_wh = self.cb_mode.findData("warehouse")
        if idx_wh >= 0:
            model = self.cb_mode.model()
            item = model.item(idx_wh)
            if item is not None:
                item.setEnabled(has_wh)
                tooltip = ("Apply warehouse mode to every manual good"
                           if has_wh else "City has no warehouse")
                item.setToolTip(tooltip)

    def _on_action_changed(self, _idx: int) -> None:
        action = self.cb_action.currentData()
        if action is None:
            return
        self.action_apply.emit(self.section_idx, int(action))
        self.cb_action.blockSignals(True)
        self.cb_action.setCurrentIndex(0)
        self.cb_action.blockSignals(False)

    def _on_mode_changed(self, _idx: int) -> None:
        mode = self.cb_mode.currentData()
        if mode is None:
            return
        self.mode_apply.emit(self.section_idx, str(mode))
        self.cb_mode.blockSignals(True)
        self.cb_mode.setCurrentIndex(0)
        self.cb_mode.blockSignals(False)


class _BulkActionBar(QtWidgets.QFrame):
    """Toolbar visible when one or more goods are selected via checkbox."""

    action_apply = QtCore.Signal(int)        # action_value
    mode_apply = QtCore.Signal(str)          # mode
    advised_apply = QtCore.Signal()
    qty_apply = QtCore.Signal(int)           # qty_value
    clear_requested = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self._has_warehouse = False
        self._build()

    def _build(self):
        h = QtWidgets.QHBoxLayout(self)
        h.setContentsMargins(8, 4, 8, 4)
        h.setSpacing(8)

        self.lbl_count = QtWidgets.QLabel("0 selected")
        self.lbl_count.setStyleSheet("font-weight: bold;")
        h.addWidget(self.lbl_count)

        self.cb_action = QtWidgets.QComboBox()
        self.cb_action.addItem("Action…", None)
        self.cb_action.addItem(ACTION_LABEL[ACTION_AUTO], ACTION_AUTO)
        self.cb_action.addItem(ACTION_LABEL[ACTION_EXCLUDED], ACTION_EXCLUDED)
        self.cb_action.addItem(ACTION_LABEL[ACTION_MANUAL], ACTION_MANUAL)
        self.cb_action.setToolTip("Apply the same action to all selected goods")
        self.cb_action.currentIndexChanged.connect(self._on_action_changed)
        h.addWidget(self.cb_action)

        self.cb_mode = QtWidgets.QComboBox()
        self.cb_mode.addItem("Mode…", None)
        self.cb_mode.addItem(f"All: {MODE_LABEL['city']}", "city")
        self.cb_mode.addItem(f"All: {MODE_LABEL['warehouse']}", "warehouse")
        self.cb_mode.setToolTip("Apply mode to every manual selected good")
        self.cb_mode.currentIndexChanged.connect(self._on_mode_changed)
        h.addWidget(self.cb_mode)

        btn_adv = QtWidgets.QToolButton()
        btn_adv.setText("💰 Apply recommended prices")
        btn_adv.setToolTip(
            "Apply recommended buy/sell prices to every manual selected good")
        btn_adv.clicked.connect(self.advised_apply)
        h.addWidget(btn_adv)

        h.addSpacing(4)
        h.addWidget(QtWidgets.QLabel("Qty:"))
        self.qty_slider = QtySlider()
        self.qty_slider.setMinimumWidth(210)
        self.qty_slider.setMaximumWidth(240)
        h.addWidget(self.qty_slider)
        btn_qty = QtWidgets.QToolButton()
        btn_qty.setText("Apply")
        btn_qty.setToolTip("Set this quantity on load+unload of every manual selected good")
        btn_qty.clicked.connect(lambda: self.qty_apply.emit(self.qty_slider.value()))
        h.addWidget(btn_qty)

        h.addStretch(1)

        btn_clear = QtWidgets.QToolButton()
        btn_clear.setText("Clear selection")
        btn_clear.clicked.connect(self.clear_requested)
        h.addWidget(btn_clear)

    def set_count(self, n: int) -> None:
        self.lbl_count.setText(f"{n} selected")

    def set_has_warehouse(self, has_wh: bool) -> None:
        self._has_warehouse = has_wh
        idx_wh = self.cb_mode.findData("warehouse")
        if idx_wh >= 0:
            model = self.cb_mode.model()
            item = model.item(idx_wh)
            if item is not None:
                item.setEnabled(has_wh)

    def _on_action_changed(self, _idx: int) -> None:
        action = self.cb_action.currentData()
        if action is None:
            return
        self.action_apply.emit(int(action))
        self.cb_action.blockSignals(True)
        self.cb_action.setCurrentIndex(0)
        self.cb_action.blockSignals(False)

    def _on_mode_changed(self, _idx: int) -> None:
        mode = self.cb_mode.currentData()
        if mode is None:
            return
        self.mode_apply.emit(str(mode))
        self.cb_mode.blockSignals(True)
        self.cb_mode.setCurrentIndex(0)
        self.cb_mode.blockSignals(False)


class GoodsTable(QtWidgets.QWidget):
    """Inline table with all 20 goods editable, grouped in 5 sections + multi-select bar."""

    # Existing signals (already handled by MainWindow)
    advised_price_requested = QtCore.Signal(int, str, str)
    action_changed = QtCore.Signal(int, int)
    trade_changed = QtCore.Signal(int, str, str, int, int)

    copy_good_requested = QtCore.Signal(int)
    paste_good_requested = QtCore.Signal(int)
    reset_good_requested = QtCore.Signal(int)

    # Section quick commands
    section_action_apply = QtCore.Signal(int, int)
    section_mode_apply = QtCore.Signal(int, str)
    section_advised_apply = QtCore.Signal(int)
    section_qty_apply = QtCore.Signal(int, int)

    # Bulk (multi-select) commands; first arg is the gid list
    bulk_action_apply = QtCore.Signal(list, int)
    bulk_mode_apply = QtCore.Signal(list, str)
    bulk_advised_apply = QtCore.Signal(list)
    bulk_qty_apply = QtCore.Signal(list, int)

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
        self._suppress = False
        self._row_widgets: list[dict] = [{} for _ in range(20)]
        self._section_headers: list[_SectionHeaderWidget] = []
        self._select_checkboxes: list[QtWidgets.QCheckBox] = [None] * 20  # type: ignore
        self._selected_gids: set[int] = set()
        self._build()

    def _build(self):
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)

        # Bulk action bar (hidden until any checkbox is ticked)
        self.bulk_bar = _BulkActionBar()
        self.bulk_bar.setVisible(False)
        self.bulk_bar.action_apply.connect(self._emit_bulk_action)
        self.bulk_bar.mode_apply.connect(self._emit_bulk_mode)
        self.bulk_bar.advised_apply.connect(self._emit_bulk_advised)
        self.bulk_bar.qty_apply.connect(self._emit_bulk_qty)
        self.bulk_bar.clear_requested.connect(self.clear_selection)
        v.addWidget(self.bulk_bar)

        self.table = QtWidgets.QTableWidget(self.N_ROWS, self.N_COLS)
        self.table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        self.table.setHorizontalHeaderLabels([
            "", "Good", "Action",
            "Mode", "Qty", "€/t", "💰",
            "Mode", "Qty", "€/t", "💰",
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.table.setIconSize(QtCore.QSize(28, 28))
        self.table.setShowGrid(True)
        self.table.setAlternatingRowColors(True)

        h = self.table.horizontalHeader()
        h.setSectionResizeMode(self.COL_ICON, QtWidgets.QHeaderView.Interactive)
        for c in range(1, self.N_COLS):
            h.setSectionResizeMode(c, QtWidgets.QHeaderView.Interactive)
        self.table.setColumnWidth(self.COL_ICON,    60)   # checkbox + icon
        self.table.setColumnWidth(self.COL_NAME,   110)
        self.table.setColumnWidth(self.COL_ACTION, 100)
        self.table.setColumnWidth(self.COL_L_MODE,  90)
        self.table.setColumnWidth(self.COL_L_QTY,  220)
        self.table.setColumnWidth(self.COL_L_PRICE,220)
        self.table.setColumnWidth(self.COL_L_ADV,   90)
        self.table.setColumnWidth(self.COL_U_MODE,  90)
        self.table.setColumnWidth(self.COL_U_QTY,  220)
        self.table.setColumnWidth(self.COL_U_PRICE,220)
        self.table.setColumnWidth(self.COL_U_ADV,   90)

        # Build section headers + good rows
        for sec_idx, (title, gids) in enumerate(GOOD_SECTIONS):
            header_row = sec_idx * 5
            self.table.setSpan(header_row, 0, 1, self.N_COLS)
            self.table.setRowHeight(header_row, 42)
            section_w = _SectionHeaderWidget(sec_idx, title)
            section_w.action_apply.connect(self.section_action_apply)
            section_w.mode_apply.connect(self.section_mode_apply)
            section_w.advised_apply.connect(self.section_advised_apply)
            section_w.qty_apply.connect(self.section_qty_apply)
            self.table.setCellWidget(header_row, 0, section_w)
            self._section_headers.append(section_w)

            for gid in gids:
                self._build_good_row(gid)

        v.addWidget(self.table)
        self.setEnabled(False)

    def _build_good_row(self, gid: int) -> None:
        row = _row_for_gid(gid)
        g = self.store.goods_by_id[gid]

        # Icon column: composite [checkbox] + [icon label]
        icon_w = QtWidgets.QWidget()
        ih = QtWidgets.QHBoxLayout(icon_w)
        ih.setContentsMargins(2, 0, 2, 0)
        ih.setSpacing(4)
        checkbox = QtWidgets.QCheckBox()
        checkbox.setToolTip("Select this good for bulk actions")
        checkbox.stateChanged.connect(
            lambda state, gid=gid: self._on_select_changed(gid, state))
        ih.addWidget(checkbox)
        icon_lbl = QtWidgets.QLabel()
        icon_lbl.setPixmap(good_icon(gid).pixmap(28, 28))
        ih.addWidget(icon_lbl)
        ih.addStretch(0)
        self.table.setCellWidget(row, self.COL_ICON, icon_w)
        self._select_checkboxes[gid] = checkbox

        it_name = QtWidgets.QTableWidgetItem(g["name_en"])
        it_name.setFlags(it_name.flags() & ~QtCore.Qt.ItemIsEditable)
        it_name.setData(QtCore.Qt.UserRole, gid)
        self.table.setItem(row, self.COL_NAME, it_name)

        cb_action = QtWidgets.QComboBox()
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
            cb_mode = QtWidgets.QComboBox()
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
            btn_adv.setText("💰 —")
            btn_adv.setToolTipDuration(0)
            btn_adv.setMinimumWidth(80)
            btn_adv.clicked_with_mods.connect(
                lambda mods, gid=gid, side=side: self._on_adv_button(gid, side, mods))
            self.table.setCellWidget(row, c_adv, btn_adv)

            row_w[f"{side}_mode"]  = cb_mode
            row_w[f"{side}_qty"]   = qty_w
            row_w[f"{side}_price"] = price_w
            row_w[f"{side}_adv"]   = btn_adv

        self._row_widgets[gid] = row_w
        self.table.setRowHeight(row, 38)

    # --- public API ---------------------------------------------------

    def set_context(self, stop: dict | None, route_excluded: list[int],
                    city_key: str | None, city_has_warehouse: bool):
        self._stop = stop
        self._route_excluded = list(route_excluded or [])
        self._city_has_warehouse = city_has_warehouse
        self._city_key = city_key
        self.setEnabled(stop is not None)
        for sh in self._section_headers:
            sh.set_has_warehouse(city_has_warehouse)
        self.bulk_bar.set_has_warehouse(city_has_warehouse)
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
        self._update_bulk_bar()

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
                        w[f"{side}_adv"].setText("💰 —")
                        w[f"{side}_adv"].setEnabled(False)
                        self._set_side_enabled(gid, side, False)
                    self._set_row_excluded_style(gid, False, False)
                return
            stop = self._stop
            for gid in range(20):
                w = self._row_widgets[gid]
                action = stop["actions"][gid]
                w["action"].setCurrentIndex(w["action"].findData(action))
                manual = (action == ACTION_MANUAL)
                route_excluded = gid in self._route_excluded
                stop_excluded = (action == ACTION_EXCLUDED)
                self._set_row_excluded_style(gid, route_excluded, stop_excluded)
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
                        btn.setText(f"💰 {adv}{star}")
                        btn.setEnabled(manual)
                    else:
                        btn.setText("💰 —")
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
            f"<i>Click</i>: apply only to this good, {label} side<br>"
            f"<i>Ctrl+Click</i>: apply to load+unload of this good<br>"
            f"<i>Shift+Click</i>: apply to every manual good, {label} side<br>"
            f"<i>Ctrl+Shift+Click</i>: apply to every manual good, both sides"
        )

    def _set_side_enabled(self, gid: int, side: str, enabled: bool):
        w = self._row_widgets[gid]
        w[f"{side}_mode"].setEnabled(enabled)
        w[f"{side}_qty"].setEnabled(enabled)

    def _set_row_excluded_style(self, gid: int, route_excluded: bool, stop_excluded: bool):
        """Visual style for excluded goods.

        - route_excluded: globally excluded across all stops -> strikethrough red
        - stop_excluded: this stop sets ACTION_EXCLUDED        -> italic gray
        Both can coexist; route style is dominant if both are true.
        """
        row = _row_for_gid(gid)
        name_item = self.table.item(row, self.COL_NAME)
        if not name_item:
            return
        font = name_item.font()
        font.setStrikeOut(False)
        font.setItalic(False)
        if route_excluded:
            font.setStrikeOut(True)
            name_item.setForeground(QtGui.QBrush(QtGui.QColor(180, 50, 50)))
            name_item.setToolTip("Excluded by route (global exclusion list)")
        elif stop_excluded:
            font.setItalic(True)
            name_item.setForeground(QtGui.QBrush(QtGui.QColor(140, 140, 140)))
            name_item.setToolTip("Excluded at this stop")
        else:
            name_item.setData(QtCore.Qt.ForegroundRole, None)
            name_item.setToolTip("")
        name_item.setFont(font)

    # --- selection ----------------------------------------------------

    def _on_select_changed(self, gid: int, state: int) -> None:
        if self._suppress:
            return
        checked = (state == QtCore.Qt.Checked.value if hasattr(QtCore.Qt.Checked, "value")
                   else state == int(QtCore.Qt.Checked))
        if checked:
            self._selected_gids.add(gid)
        else:
            self._selected_gids.discard(gid)
        self._update_bulk_bar()

    def _update_bulk_bar(self) -> None:
        n = len(self._selected_gids)
        self.bulk_bar.set_count(n)
        self.bulk_bar.setVisible(n > 0)

    def _emit_bulk_action(self, action: int) -> None:
        if not self._selected_gids:
            return
        self.bulk_action_apply.emit(sorted(self._selected_gids), int(action))

    def _emit_bulk_mode(self, mode: str) -> None:
        if not self._selected_gids:
            return
        self.bulk_mode_apply.emit(sorted(self._selected_gids), str(mode))

    def _emit_bulk_advised(self) -> None:
        if not self._selected_gids:
            return
        self.bulk_advised_apply.emit(sorted(self._selected_gids))

    def _emit_bulk_qty(self, qty: int) -> None:
        if not self._selected_gids:
            return
        self.bulk_qty_apply.emit(sorted(self._selected_gids), int(qty))

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
        shift = bool(mods & QtCore.Qt.ShiftModifier)
        sides = "both" if ctrl else side
        scope = "all" if shift else "current"
        self.advised_price_requested.emit(good_id, sides, scope)

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
