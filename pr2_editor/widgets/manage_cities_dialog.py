"""Dialog "Gestisci città": modifica override di partita (magazzino, nazione, prezzi)."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ..constants import NATIONS_AVAILABLE, WAREHOUSE_TONS_PER_LEVEL
from ..icons import good_icon
from ..store import Store


class ManageCitiesDialog(QtWidgets.QDialog):
    """Modifica per partita corrente: magazzini, nazioni, override prezzi consigliati."""

    def __init__(self, store: Store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("Gestisci città — magazzini, nazioni, prezzi")
        self.resize(1180, 740)
        self._current_city_key: str | None = None
        self._suppress = False
        self._build()
        if self.lst.count() > 0:
            self.lst.setCurrentRow(0)

    def _build(self):
        outer = QtWidgets.QVBoxLayout(self)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        # --- sinistra: filtri + lista citta ---
        left = QtWidgets.QWidget()
        lv = QtWidgets.QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Cerca:"))
        self.ed_search = QtWidgets.QLineEdit()
        self.ed_search.setPlaceholderText("nome città...")
        self.ed_search.textChanged.connect(self._refresh_filter)
        row.addWidget(self.ed_search, 1)
        lv.addLayout(row)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Nazione:"))
        self.cb_nation_filter = QtWidgets.QComboBox()
        self.cb_nation_filter.addItem("(tutte)", None)
        for n in NATIONS_AVAILABLE:
            self.cb_nation_filter.addItem(n, n)
        self.cb_nation_filter.currentIndexChanged.connect(self._refresh_filter)
        row.addWidget(self.cb_nation_filter, 1)
        lv.addLayout(row)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Ruolo:"))
        self.cb_role_filter = QtWidgets.QComboBox()
        self.cb_role_filter.addItem("(tutti)", None)
        self.cb_role_filter.addItem("V (vicerè/capitale)", "V")
        self.cb_role_filter.addItem("G (governatorato)", "G")
        self.cb_role_filter.addItem("normale", "_NONE")
        self.cb_role_filter.currentIndexChanged.connect(self._refresh_filter)
        row.addWidget(self.cb_role_filter, 1)
        lv.addLayout(row)

        self.cb_only_overrides = QtWidgets.QCheckBox("Solo città con override")
        self.cb_only_overrides.toggled.connect(self._refresh_filter)
        lv.addWidget(self.cb_only_overrides)

        self.lst = QtWidgets.QListWidget()
        self.lst.currentItemChanged.connect(self._on_city_selected)
        lv.addWidget(self.lst, 1)

        self._populate_list()

        # --- destra: form citta selezionata ---
        right = QtWidgets.QWidget()
        rv = QtWidgets.QVBoxLayout(right)
        rv.setContentsMargins(8, 0, 0, 0)

        self.header_label = QtWidgets.QLabel("(seleziona una città)")
        self.header_label.setStyleSheet("font-size:14pt; font-weight:bold;")
        rv.addWidget(self.header_label)
        self.meta_label = QtWidgets.QLabel("")
        self.meta_label.setTextFormat(QtCore.Qt.RichText)
        self.meta_label.setWordWrap(True)
        rv.addWidget(self.meta_label)

        sep = QtWidgets.QFrame(); sep.setFrameShape(QtWidgets.QFrame.HLine); rv.addWidget(sep)

        form_box = QtWidgets.QGroupBox("Stato corrente")
        fl = QtWidgets.QGridLayout(form_box)
        fl.addWidget(QtWidgets.QLabel("Livello magazzino:"), 0, 0)
        self.sp_warehouse = QtWidgets.QSpinBox()
        self.sp_warehouse.setRange(0, 99)
        self.sp_warehouse.setSpecialValueText("0 (nessuno)")
        self.sp_warehouse.valueChanged.connect(self._on_warehouse_changed)
        fl.addWidget(self.sp_warehouse, 0, 1)
        self.lbl_warehouse_capacity = QtWidgets.QLabel("0 t")
        fl.addWidget(self.lbl_warehouse_capacity, 0, 2)
        self.btn_warehouse_reset = QtWidgets.QPushButton("Resetta")
        self.btn_warehouse_reset.setToolTip("Imposta livello a 0 (nessun magazzino)")
        self.btn_warehouse_reset.clicked.connect(lambda: self.sp_warehouse.setValue(0))
        fl.addWidget(self.btn_warehouse_reset, 0, 3)

        fl.addWidget(QtWidgets.QLabel("Nazione corrente:"), 1, 0)
        self.cb_nation = QtWidgets.QComboBox()
        for n in NATIONS_AVAILABLE:
            self.cb_nation.addItem(n, n)
        self.cb_nation.currentIndexChanged.connect(self._on_nation_changed)
        fl.addWidget(self.cb_nation, 1, 1)
        self.lbl_nation_default = QtWidgets.QLabel("")
        fl.addWidget(self.lbl_nation_default, 1, 2)
        self.btn_nation_reset = QtWidgets.QPushButton("Resetta")
        self.btn_nation_reset.setToolTip("Ripristina la nazione di default")
        self.btn_nation_reset.clicked.connect(self._reset_nation)
        fl.addWidget(self.btn_nation_reset, 1, 3)
        fl.setColumnStretch(1, 1)
        fl.setColumnStretch(2, 1)

        rv.addWidget(form_box)

        box_prices = QtWidgets.QGroupBox("Override prezzi consigliati per merce (vuoto = usa default globale)")
        bp = QtWidgets.QVBoxLayout(box_prices)
        self.prices_table = QtWidgets.QTableWidget(20, 6)
        self.prices_table.setHorizontalHeaderLabels(
            ["Merce", "Buy default", "Buy override", "Sell default", "Sell override", ""]
        )
        self.prices_table.verticalHeader().setVisible(False)
        self.prices_table.setAlternatingRowColors(True)
        self.prices_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.prices_table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.prices_table.setIconSize(QtCore.QSize(22, 22))
        hh = self.prices_table.horizontalHeader()
        hh.setSectionResizeMode(0, QtWidgets.QHeaderView.Interactive)
        for c in range(1, 6):
            hh.setSectionResizeMode(c, QtWidgets.QHeaderView.Interactive)
        self.prices_table.setColumnWidth(0, 150)
        self.prices_table.setColumnWidth(1, 100)
        self.prices_table.setColumnWidth(2, 130)
        self.prices_table.setColumnWidth(3, 100)
        self.prices_table.setColumnWidth(4, 130)
        self.prices_table.setColumnWidth(5, 60)

        self._price_buy_widgets: list[QtWidgets.QSpinBox] = []
        self._price_sell_widgets: list[QtWidgets.QSpinBox] = []

        for gid, g in enumerate(self.store.config["goods"]):
            it_name = QtWidgets.QTableWidgetItem(good_icon(gid), g["name_it"])
            it_name.setFlags(it_name.flags() & ~QtCore.Qt.ItemIsEditable)
            self.prices_table.setItem(gid, 0, it_name)

            buy_def = g.get("price_buy_advised")
            it_buy_def = QtWidgets.QTableWidgetItem(str(buy_def) if buy_def else "—")
            it_buy_def.setFlags(it_buy_def.flags() & ~QtCore.Qt.ItemIsEditable)
            it_buy_def.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            it_buy_def.setForeground(QtGui.QColor(120, 120, 120))
            self.prices_table.setItem(gid, 1, it_buy_def)

            sp_buy = QtWidgets.QSpinBox()
            sp_buy.setRange(-1, 999_999)
            sp_buy.setSpecialValueText("(default)")
            sp_buy.setAlignment(QtCore.Qt.AlignRight)
            sp_buy.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
            sp_buy.valueChanged.connect(
                lambda v, gid=gid: self._on_price_changed(gid, "buy", v))
            self.prices_table.setCellWidget(gid, 2, sp_buy)
            self._price_buy_widgets.append(sp_buy)

            sell_def = g.get("price_sell_advised")
            it_sell_def = QtWidgets.QTableWidgetItem(str(sell_def) if sell_def else "—")
            it_sell_def.setFlags(it_sell_def.flags() & ~QtCore.Qt.ItemIsEditable)
            it_sell_def.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            it_sell_def.setForeground(QtGui.QColor(120, 120, 120))
            self.prices_table.setItem(gid, 3, it_sell_def)

            sp_sell = QtWidgets.QSpinBox()
            sp_sell.setRange(-1, 999_999)
            sp_sell.setSpecialValueText("(default)")
            sp_sell.setAlignment(QtCore.Qt.AlignRight)
            sp_sell.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
            sp_sell.valueChanged.connect(
                lambda v, gid=gid: self._on_price_changed(gid, "sell", v))
            self.prices_table.setCellWidget(gid, 4, sp_sell)
            self._price_sell_widgets.append(sp_sell)

            btn_reset = QtWidgets.QToolButton()
            btn_reset.setText("⟲")
            btn_reset.setToolTip(f"Resetta override per '{g['name_it']}' a default")
            btn_reset.clicked.connect(lambda _, gid=gid: self._reset_prices_for_good(gid))
            self.prices_table.setCellWidget(gid, 5, btn_reset)

        self.prices_table.resizeRowsToContents()
        bp.addWidget(self.prices_table)

        bb_prices = QtWidgets.QHBoxLayout()
        self.btn_reset_all_prices = QtWidgets.QPushButton("Resetta tutti i prezzi a default")
        self.btn_reset_all_prices.clicked.connect(self._reset_all_prices)
        bb_prices.addWidget(self.btn_reset_all_prices)
        bb_prices.addStretch(1)
        bp.addLayout(bb_prices)
        rv.addWidget(box_prices, 1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 900])
        outer.addWidget(splitter, 1)

        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        bb.accepted.connect(self.accept)
        outer.addWidget(bb)

        self._set_form_enabled(False)
        self._refresh_filter()

    # --- popola lista ---------------------------------------------------

    def _populate_list(self):
        self.lst.clear()
        for c in self.store.config["cities"]:
            it = QtWidgets.QListWidgetItem()
            it.setData(QtCore.Qt.UserRole, c["key"])
            self._update_list_item_text(it, c)
            self.lst.addItem(it)

    def _update_list_item_text(self, it: QtWidgets.QListWidgetItem, c: dict):
        ckey = c["key"]
        ov = self.store.user_state["city_overrides"].get(ckey, {})
        wl = self.store.city_warehouse_level(ckey)
        nation = self.store.city_nation(ckey)
        badges: list[str] = []
        if c.get("role"):
            badges.append(c["role"])
        if wl > 0:
            badges.append(f"M{wl}")
        if "nation" in ov:
            badges.append(f"→{nation}")
        n_p = len(ov.get("advised_prices", {}))
        if n_p:
            badges.append(f"P{n_p}")
        badge_str = (" [" + ",".join(badges) + "]") if badges else ""
        it.setText(f"{c['id']:>3}  {c['name']}  ·  {nation}{badge_str}")
        font = it.font()
        font.setBold(bool(ov))
        it.setFont(font)

    def _refresh_filter(self):
        q = self.ed_search.text().lower().strip()
        nation = self.cb_nation_filter.currentData()
        role = self.cb_role_filter.currentData()
        only_ov = self.cb_only_overrides.isChecked()
        overrides = self.store.user_state["city_overrides"]
        for i in range(self.lst.count()):
            it = self.lst.item(i)
            ckey = it.data(QtCore.Qt.UserRole)
            city = self.store.cities_by_key[ckey]
            ok_name = (q == "" or q in city["name"].lower())
            ok_nation = (nation is None or self.store.city_nation(ckey) == nation)
            crole = city.get("role")
            if role is None:
                ok_role = True
            elif role == "_NONE":
                ok_role = (crole is None)
            else:
                ok_role = (crole == role)
            ok_ov = (not only_ov) or bool(overrides.get(ckey))
            it.setHidden(not (ok_name and ok_nation and ok_role and ok_ov))

    # --- selezione + form -----------------------------------------------

    def _on_city_selected(self, current, _previous):
        if current is None:
            self._current_city_key = None
            self._set_form_enabled(False)
            self.header_label.setText("(seleziona una città)")
            self.meta_label.setText("")
            return
        ckey = current.data(QtCore.Qt.UserRole)
        self._current_city_key = ckey
        self._set_form_enabled(True)
        self._load_city_to_form(ckey)

    def _set_form_enabled(self, enabled: bool):
        for w in (self.sp_warehouse, self.btn_warehouse_reset,
                  self.cb_nation, self.btn_nation_reset,
                  self.prices_table, self.btn_reset_all_prices):
            w.setEnabled(enabled)

    def _load_city_to_form(self, ckey: str):
        city = self.store.cities_by_key[ckey]
        self._suppress = True
        try:
            self.header_label.setText(f"{city['name']} (id {city['id']})")
            role = city.get("role") or "—"
            default_nation = city["nation"]
            produces = ", ".join(
                self.store.goods_by_id[g]["name_it"] for g in city.get("produces", []))
            self.meta_label.setText(
                f"<b>nazione default:</b> {default_nation} &nbsp; "
                f"<b>ruolo:</b> {role}<br>"
                f"<b>produce:</b> {produces or '—'}"
            )

            wl = self.store.city_warehouse_level(ckey)
            self.sp_warehouse.setValue(wl)
            self.lbl_warehouse_capacity.setText(f"{wl * WAREHOUSE_TONS_PER_LEVEL} t")

            cur_nation = self.store.city_nation(ckey)
            idx = self.cb_nation.findData(cur_nation)
            if idx < 0:
                self.cb_nation.addItem(cur_nation, cur_nation)
                idx = self.cb_nation.findData(cur_nation)
            self.cb_nation.setCurrentIndex(idx)
            self.lbl_nation_default.setText(f"(default: {default_nation})")

            ov = self.store.user_state["city_overrides"].get(ckey, {}).get("advised_prices", {})
            for gid in range(20):
                pg = ov.get(str(gid), {})
                buy_v = pg.get("buy")
                sell_v = pg.get("sell")
                self._price_buy_widgets[gid].setValue(-1 if buy_v is None else int(buy_v))
                self._price_sell_widgets[gid].setValue(-1 if sell_v is None else int(sell_v))
        finally:
            self._suppress = False

    # --- handlers -------------------------------------------------------

    def _on_warehouse_changed(self, value: int):
        if self._suppress or not self._current_city_key:
            return
        self.store.set_city_warehouse_level(self._current_city_key, value)
        self.lbl_warehouse_capacity.setText(f"{value * WAREHOUSE_TONS_PER_LEVEL} t")
        self._refresh_current_list_item()

    def _on_nation_changed(self, _idx: int):
        if self._suppress or not self._current_city_key:
            return
        new_nation = self.cb_nation.currentData()
        self.store.set_city_nation(self._current_city_key, new_nation)
        self._refresh_current_list_item()

    def _reset_nation(self):
        if not self._current_city_key:
            return
        default = self.store.cities_by_key[self._current_city_key]["nation"]
        idx = self.cb_nation.findData(default)
        if idx >= 0:
            self.cb_nation.setCurrentIndex(idx)

    def _on_price_changed(self, gid: int, side: str, value: int):
        if self._suppress or not self._current_city_key:
            return
        v = None if value < 0 else int(value)
        self.store.set_city_advised_price(self._current_city_key, gid, side, v)
        self._refresh_current_list_item()

    def _reset_prices_for_good(self, gid: int):
        self._price_buy_widgets[gid].setValue(-1)
        self._price_sell_widgets[gid].setValue(-1)

    def _reset_all_prices(self):
        for gid in range(20):
            self._reset_prices_for_good(gid)

    def _refresh_current_list_item(self):
        it = self.lst.currentItem()
        if not it:
            return
        ckey = it.data(QtCore.Qt.UserRole)
        self._update_list_item_text(it, self.store.cities_by_key[ckey])
