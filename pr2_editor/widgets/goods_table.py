"""GoodsTable: tabella inline editabile per le 20 merci di uno stop, raggruppate in 5 sezioni."""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ..constants import (
    ACTION_AUTO,
    ACTION_EXCLUDED,
    ACTION_LABEL,
    ACTION_MANUAL,
    GOOD_SECTIONS,
    MODE_LABEL,
    QTY_MAX,
)
from ..icons import good_icon
from ..store import Store
from .row_widgets import PriceSlider, QtySlider, _ModifierToolButton


def _row_for_gid(gid: int) -> int:
    """Mappa good_id (0..19) all'indice di riga nella tabella (header occupano rows 0,5,10,15,20)."""
    return 1 + (gid // 4) * 5 + (gid % 4)


def _gid_for_row(row: int) -> int | None:
    """Ritorna il good_id per la riga, o None se la riga è un header di sezione."""
    if row < 0 or row >= 25 or row % 5 == 0:
        return None
    return (row // 5) * 4 + (row % 5 - 1)


class _SectionHeaderWidget(QtWidgets.QWidget):
    """Riga header di una sezione con comandi rapidi per le 4 merci."""

    # Tutti i segnali portano l'indice di sezione (0..4) come primo argomento.
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

        # Dropdown azione
        self.cb_action = QtWidgets.QComboBox()
        self.cb_action.addItem("Azione…", None)
        self.cb_action.addItem(ACTION_LABEL[ACTION_AUTO], ACTION_AUTO)
        self.cb_action.addItem(ACTION_LABEL[ACTION_EXCLUDED], ACTION_EXCLUDED)
        self.cb_action.addItem(ACTION_LABEL[ACTION_MANUAL], ACTION_MANUAL)
        self.cb_action.setToolTip(
            "Applica la stessa azione a tutte e 4 le merci della sezione")
        self.cb_action.currentIndexChanged.connect(self._on_action_changed)
        h.addWidget(self.cb_action)

        # Dropdown mode (citta / magazzino)
        self.cb_mode = QtWidgets.QComboBox()
        self.cb_mode.addItem("Modalità…", None)
        self.cb_mode.addItem(f"Tutto: {MODE_LABEL['city']}", "city")
        self.cb_mode.addItem(f"Tutto: {MODE_LABEL['warehouse']}", "warehouse")
        self.cb_mode.setToolTip(
            "Applica la modalità (carico+scarico) a tutte le merci manuali della sezione")
        self.cb_mode.currentIndexChanged.connect(self._on_mode_changed)
        h.addWidget(self.cb_mode)

        # Bottone applica prezzi consigliati
        btn_adv = QtWidgets.QToolButton()
        btn_adv.setText("💰 Applica prezzi consigliati")
        btn_adv.setToolTip(
            "Applica i prezzi consigliati buy/sell a tutte le merci manuali della sezione")
        btn_adv.clicked.connect(lambda: self.advised_apply.emit(self.section_idx))
        h.addWidget(btn_adv)

        # Input quantità + applica
        h.addSpacing(4)
        h.addWidget(QtWidgets.QLabel("Qty:"))
        self.sp_qty = QtWidgets.QSpinBox()
        self.sp_qty.setRange(0, QTY_MAX)
        self.sp_qty.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.sp_qty.setMinimumWidth(70)
        self.sp_qty.setMaximumWidth(80)
        self.sp_qty.setSpecialValueText("0")
        h.addWidget(self.sp_qty)
        btn_qty = QtWidgets.QToolButton()
        btn_qty.setText("Applica")
        btn_qty.setToolTip(
            "Imposta questa quantità a carico+scarico di tutte le merci manuali della sezione")
        btn_qty.clicked.connect(lambda: self.qty_apply.emit(self.section_idx, int(self.sp_qty.value())))
        h.addWidget(btn_qty)

        h.addStretch(1)

    def set_has_warehouse(self, has_wh: bool) -> None:
        self._has_warehouse = has_wh
        # Disabilita l'opzione "magazzino" nel dropdown se la città non ha magazzino
        idx_wh = self.cb_mode.findData("warehouse")
        if idx_wh >= 0:
            model = self.cb_mode.model()
            item = model.item(idx_wh)
            if item is not None:
                item.setEnabled(has_wh)
                tooltip = ("Applica magazzino a tutte le merci manuali"
                           if has_wh else "La città non ha magazzino")
                item.setToolTip(tooltip)

    def _on_action_changed(self, _idx: int) -> None:
        action = self.cb_action.currentData()
        if action is None:
            return
        self.action_apply.emit(self.section_idx, int(action))
        # Reset al placeholder dopo l'apply
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


class GoodsTable(QtWidgets.QWidget):
    """Tabella inline con tutte le 20 merci editabili in riga, raggruppate in 5 sezioni."""

    # Segnali esistenti (mainwindow li gestiva gia')
    advised_price_requested = QtCore.Signal(int, str, str)  # good_id, sides, scope
    action_changed = QtCore.Signal(int, int)                # good_id, new_action
    trade_changed = QtCore.Signal(int, str, str, int, int)  # good_id, side, mode, qty, price

    copy_good_requested = QtCore.Signal(int)
    paste_good_requested = QtCore.Signal(int)
    reset_good_requested = QtCore.Signal(int)

    # Nuovi segnali per le azioni di sezione
    section_action_apply = QtCore.Signal(int, int)   # section_idx, action_value
    section_mode_apply = QtCore.Signal(int, str)     # section_idx, mode
    section_advised_apply = QtCore.Signal(int)       # section_idx
    section_qty_apply = QtCore.Signal(int, int)      # section_idx, qty

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

    N_ROWS = 25  # 5 header + 20 merci

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
        self._build()

    def _build(self):
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)

        self.table = QtWidgets.QTableWidget(self.N_ROWS, self.N_COLS)
        self.table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        self.table.setHorizontalHeaderLabels([
            "", "Merce", "Azione",
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
        h.setSectionResizeMode(self.COL_ICON, QtWidgets.QHeaderView.ResizeToContents)
        for c in range(1, self.N_COLS):
            h.setSectionResizeMode(c, QtWidgets.QHeaderView.Interactive)
        self.table.setColumnWidth(self.COL_NAME,    100)
        self.table.setColumnWidth(self.COL_ACTION,  100)
        self.table.setColumnWidth(self.COL_L_MODE,   90)
        self.table.setColumnWidth(self.COL_L_QTY,   140)
        self.table.setColumnWidth(self.COL_L_PRICE, 130)
        self.table.setColumnWidth(self.COL_L_ADV,    90)
        self.table.setColumnWidth(self.COL_U_MODE,   90)
        self.table.setColumnWidth(self.COL_U_QTY,   140)
        self.table.setColumnWidth(self.COL_U_PRICE, 130)
        self.table.setColumnWidth(self.COL_U_ADV,    90)

        # Costruisce header di sezione + righe merci
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

        it_icon = QtWidgets.QTableWidgetItem(good_icon(gid), "")
        it_icon.setFlags(it_icon.flags() & ~QtCore.Qt.ItemIsEditable)
        self.table.setItem(row, self.COL_ICON, it_icon)
        it_name = QtWidgets.QTableWidgetItem(g["name_it"])
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

    # --- API publica ----------------------------------------------------

    def set_context(self, stop: dict | None, route_excluded: list[int],
                    city_key: str | None, city_has_warehouse: bool):
        self._stop = stop
        self._route_excluded = list(route_excluded or [])
        self._city_has_warehouse = city_has_warehouse
        self._city_key = city_key
        self.setEnabled(stop is not None)
        for sh in self._section_headers:
            sh.set_has_warehouse(city_has_warehouse)
        self._refresh()

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
                return
            stop = self._stop
            for gid in range(20):
                w = self._row_widgets[gid]
                action = stop["actions"][gid]
                w["action"].setCurrentIndex(w["action"].findData(action))
                manual = (action == ACTION_MANUAL)
                self._set_row_excluded_style(gid, gid in self._route_excluded)
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
        label = "compra" if side == "load" else "vendi"
        if adv <= 0:
            return f"Nessun prezzo consigliato '{label}' impostato."
        src = " (override per città)" if override else ""
        return (
            f"Prezzo consigliato {label}: <b>{adv}</b>{src}<br>"
            f"<i>Click</i>: applica solo a questa merce, lato {label}<br>"
            f"<i>Ctrl+Click</i>: applica a carico+scarico di questa merce<br>"
            f"<i>Shift+Click</i>: applica a tutte le merci manuali, lato {label}<br>"
            f"<i>Ctrl+Shift+Click</i>: applica a tutte le manuali, entrambi i lati"
        )

    def _set_side_enabled(self, gid: int, side: str, enabled: bool):
        w = self._row_widgets[gid]
        w[f"{side}_mode"].setEnabled(enabled)
        w[f"{side}_qty"].setEnabled(enabled)

    def _set_row_excluded_style(self, gid: int, excluded: bool):
        row = _row_for_gid(gid)
        name_it = self.table.item(row, self.COL_NAME)
        if not name_it:
            return
        font = name_it.font()
        font.setStrikeOut(excluded)
        name_it.setFont(font)
        name_it.setToolTip("Esclusa a livello di rotta" if excluded else "")

    # --- handlers segnali interni --------------------------------------

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
        gname = self.store.goods_by_id[gid]["name_it"]
        menu = QtWidgets.QMenu(self)
        a_copy = menu.addAction(f"Copia configurazione di '{gname}'")
        a_paste = menu.addAction(f"Incolla configurazione su '{gname}'")
        menu.addSeparator()
        a_reset = menu.addAction(f"Resetta '{gname}' a Automatica")
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
            (f"Mercato: {g['price_market']}", g['price_market']),
            (f"Max: {g['price_max']}", g['price_max']),
        ]:
            if value <= 0:
                continue
            act = menu.addAction(label)
            act.triggered.connect(lambda _, v=value: (sp.setValue(v), self._emit_trade(good_id, side)))
        if menu.actions():
            menu.exec(sp.mapToGlobal(pos))
