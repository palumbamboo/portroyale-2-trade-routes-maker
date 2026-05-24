"""GUI per editare rotte commerciali di Port Royale 2.

Avvio:
    python gui.py
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

import ahr

# --- Costanti / paths -------------------------------------------------------

WORKSPACE = Path(__file__).resolve().parent
CONFIG_PATH = WORKSPACE / "pr2_config.json"
USER_STATE_PATH = WORKSPACE / "user_state.json"
ICONS_DIR = WORKSPACE / "icons"
ROUTES_DIR = WORKSPACE / "rotte"

APP_NAME = "Editor Rotte Port Royale 2"
APP_VERSION = "0.4.0"

QTY_MAX = 0xFFFF
WAREHOUSE_PRICE = 0xFFFFFFFF

ACTION_AUTO = 1
ACTION_EXCLUDED = 0
ACTION_MANUAL = 2

ACTION_LABEL = {ACTION_AUTO: "Automatica", ACTION_EXCLUDED: "Esclusa qui", ACTION_MANUAL: "Manuale"}
MODE_LABEL = {"city": "Città", "warehouse": "Magazzino"}


# --- Icone -------------------------------------------------------------------

GOOD_ICON_FILE: dict[int, str | None] = {
    0:  "ble.png",            1:  "fruits.png",  2:  "bois.png",   3:  "briques.png",
    4:  "mais.png",           5:  "sucre.png",   6:  "cotton.png", 7:  "chanvre.png",
    8:  "viande.png",         9:  "vetements.png", 10: "cordes.png", 11: "rhum.png",
    12: "cafe.png",           13: "cacao.png",   14: "teinture.png", 15: "tabac.png",
    16: "textiles.png",       17: "pain.png",    18: "outils_en_metal.png", 19: "metal.png",
}


def good_icon(good_id: int) -> QtGui.QIcon:
    fname = GOOD_ICON_FILE.get(good_id)
    if fname:
        p = ICONS_DIR / fname
        if p.exists():
            return QtGui.QIcon(str(p))
    return QtGui.QIcon()


# --- Store: config + user_state --------------------------------------------

class Store(QtCore.QObject):
    user_state_changed = QtCore.Signal()

    def __init__(self, parent: QtCore.QObject | None = None):
        super().__init__(parent)
        if not CONFIG_PATH.exists():
            raise FileNotFoundError(f"pr2_config.json non trovato in {CONFIG_PATH}")
        self.config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        assert len(self.config["goods"]) == 20
        assert len(self.config["cities"]) == 60
        self.user_state = self._load_user_state()
        self.cities_by_id = {c["id"]: c for c in self.config["cities"]}
        self.cities_by_key = {c["key"]: c for c in self.config["cities"]}
        self.goods_by_id = {g["id"]: g for g in self.config["goods"]}
        self.goods_by_key = {g["key"]: g for g in self.config["goods"]}

    def _load_user_state(self) -> dict:
        if USER_STATE_PATH.exists():
            return json.loads(USER_STATE_PATH.read_text(encoding="utf-8"))
        state = {"_format": "pr2-user-state-v1", "city_overrides": {}}
        USER_STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        return state

    def save_user_state(self) -> None:
        USER_STATE_PATH.write_text(json.dumps(self.user_state, indent=2, ensure_ascii=False), encoding="utf-8")
        self.user_state_changed.emit()

    def city_nation(self, city_key: str) -> str:
        ov = self.user_state["city_overrides"].get(city_key, {})
        return ov.get("nation") or self.cities_by_key[city_key]["nation"]

    def city_warehouse_level(self, city_key: str) -> int:
        ov = self.user_state["city_overrides"].get(city_key, {})
        return int(ov.get("warehouse_level", 0))

    def city_has_warehouse(self, city_key: str) -> bool:
        return self.city_warehouse_level(city_key) > 0

    def city_advised_price(self, city_key: str, good_id: int, side: str) -> int:
        assert side in ("buy", "sell")
        ov = self.user_state["city_overrides"].get(city_key, {})
        per_good = ov.get("advised_prices", {}).get(str(good_id))
        if per_good and side in per_good and per_good[side] is not None:
            return int(per_good[side])
        key = "price_buy_advised" if side == "buy" else "price_sell_advised"
        return int(self.goods_by_id[good_id].get(key, 0) or 0)

    def set_city_advised_price(self, city_key: str, good_id: int, side: str, value: int | None) -> None:
        assert side in ("buy", "sell")
        ov = self.user_state["city_overrides"].setdefault(city_key, {})
        bag = ov.setdefault("advised_prices", {})
        per_good = bag.setdefault(str(good_id), {})
        if value is None:
            per_good.pop(side, None)
        else:
            per_good[side] = int(value)
        if not per_good:
            bag.pop(str(good_id), None)
        if not bag:
            ov.pop("advised_prices", None)
        if not ov:
            self.user_state["city_overrides"].pop(city_key, None)
        self.save_user_state()


# --- Route model -----------------------------------------------------------

class Route(QtCore.QObject):
    changed = QtCore.Signal()
    stop_changed = QtCore.Signal(int)

    def __init__(self, store: Store, doc: dict | None = None, filepath: Path | None = None):
        super().__init__()
        self.store = store
        self.doc = doc if doc else self._empty_doc()
        self.filepath = filepath
        self._dirty = False

    @staticmethod
    def _empty_doc() -> dict:
        return {"_format": "ahr-v1",
                "header": {"nstops": 0, "capacity": 0, "route_excluded_goods": []},
                "stops": []}

    @staticmethod
    def _empty_stop(city_id: int, is_start: bool) -> dict:
        return {
            "display_order": list(range(20)),
            "actions": [ACTION_AUTO] * 20,
            "action_kinds": ["auto"] * 20,
            "trades": [{
                "good": ahr.GOOD_NAMES[g],
                "load_mode": "city",  "load_price": 0,  "load_qty": 0,  "load_aux": 0,
                "unload_mode": "city","unload_price": 0,"unload_qty": 0,"unload_aux": 0,
            } for g in range(20)],
            "trailer": {
                "city_id": city_id, "const_b1": 0x00, "marker": 0x21, "const_b3": 0x00,
                "start_flag": 1 if is_start else 0, "const_b5": 0x00,
            },
        }

    @property
    def dirty(self) -> bool: return self._dirty
    def set_dirty(self, v: bool = True) -> None:
        if self._dirty != v:
            self._dirty = v
            self.changed.emit()

    @property
    def stops(self) -> list[dict]: return self.doc["stops"]
    @property
    def excluded_route(self) -> list[int]: return list(self.doc["header"].get("route_excluded_goods", []))

    def set_excluded_route(self, goods: list[int]) -> None:
        self.doc["header"]["route_excluded_goods"] = sorted(set(goods))
        self.set_dirty()
        self.changed.emit()

    def add_stop(self, city_id: int) -> int:
        idx = len(self.stops)
        if idx >= ahr.MAX_STOPS:
            raise ValueError(f"Massimo {ahr.MAX_STOPS} stop per rotta")
        self.stops.append(self._empty_stop(city_id, is_start=(idx == 0)))
        self._refresh_header_counts()
        self.set_dirty()
        self.changed.emit()
        return idx

    def remove_stop(self, idx: int) -> None:
        if 0 <= idx < len(self.stops):
            del self.stops[idx]
            self._recompute_start_flags()
            self._refresh_header_counts()
            self.set_dirty()
            self.changed.emit()

    def move_stop(self, src: int, dst: int) -> None:
        if src == dst or not (0 <= src < len(self.stops)) or not (0 <= dst < len(self.stops)):
            return
        s = self.stops.pop(src)
        self.stops.insert(dst, s)
        self._recompute_start_flags()
        self.set_dirty()
        self.changed.emit()

    def _recompute_start_flags(self) -> None:
        for i, s in enumerate(self.stops):
            s["trailer"]["start_flag"] = 1 if i == 0 else 0

    def _refresh_header_counts(self) -> None:
        self.doc["header"]["nstops"] = len(self.stops)
        self.doc["header"]["capacity"] = ahr._capacity(len(self.stops))

    def display_name(self) -> str:
        suffix = "*" if self._dirty else ""
        return (self.filepath.name if self.filepath else "(rotta senza nome)") + suffix

    def set_good_action(self, stop_idx: int, good_id: int, new_action: int) -> None:
        if not (0 <= stop_idx < len(self.stops)) or not (0 <= good_id < 20): return
        stop = self.stops[stop_idx]
        if stop["actions"][good_id] == new_action: return
        stop["actions"][good_id] = new_action
        stop["action_kinds"][good_id] = ahr.ACTION_NAMES.get(new_action, "?")
        if new_action != ACTION_MANUAL:
            t = stop["trades"][good_id]
            t["load_mode"] = "city";  t["load_price"] = 0;  t["load_qty"] = 0;  t["load_aux"] = 0
            t["unload_mode"] = "city";t["unload_price"] = 0;t["unload_qty"] = 0;t["unload_aux"] = 0
        self._rebuild_display_order(stop_idx)
        self.set_dirty()
        self.stop_changed.emit(stop_idx)

    def _rebuild_display_order(self, stop_idx: int) -> None:
        stop = self.stops[stop_idx]
        manuals = [g for g in range(20) if stop["actions"][g] == ACTION_MANUAL]
        rest = [g for g in range(20) if stop["actions"][g] != ACTION_MANUAL]
        stop["display_order"] = manuals + rest

    def set_good_trade(self, stop_idx: int, good_id: int,
                       *, side: str, mode: str, qty: int, price: int) -> None:
        if side not in ("load", "unload") or mode not in ("city", "warehouse"): return
        if not (0 <= stop_idx < len(self.stops)) or not (0 <= good_id < 20): return
        t = self.stops[stop_idx]["trades"][good_id]
        if mode == "warehouse":
            price_val = WAREHOUSE_PRICE
        else:
            price_val = max(0, min(int(price), 0xFFFFFFFE))
        qty_val = max(0, min(int(qty), QTY_MAX))
        t[f"{side}_mode"] = mode
        t[f"{side}_price"] = price_val
        t[f"{side}_qty"] = qty_val
        self.set_dirty()
        self.stop_changed.emit(stop_idx)

    @classmethod
    def from_file(cls, store: Store, path: Path) -> "Route":
        doc = ahr.decode(path.read_bytes())
        r = cls(store, doc=doc, filepath=path)
        r._dirty = False
        return r

    def save_to(self, path: Path) -> None:
        if not self.stops:
            raise ValueError("Impossibile salvare una rotta senza stop")
        data = ahr.encode(self.doc)
        path.write_bytes(data)
        self.filepath = path
        self._dirty = False
        self.changed.emit()


# --- Dialog "Aggiungi tappa" ------------------------------------------------

class AddStopDialog(QtWidgets.QDialog):
    def __init__(self, store: Store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("Aggiungi tappa")
        self.resize(560, 600)
        self.selected_city_id: int | None = None
        self._build()

    def _build(self):
        lay = QtWidgets.QVBoxLayout(self)
        f = QtWidgets.QHBoxLayout()
        f.addWidget(QtWidgets.QLabel("Cerca:"))
        self.ed_search = QtWidgets.QLineEdit()
        self.ed_search.setPlaceholderText("nome città...")
        self.ed_search.textChanged.connect(self._refresh_filter)
        f.addWidget(self.ed_search, 1)
        f.addWidget(QtWidgets.QLabel("Nazione:"))
        self.cb_nation = QtWidgets.QComboBox()
        self.cb_nation.addItem("(tutte)", None)
        for n in sorted({c["nation"] for c in self.store.config["cities"]}):
            self.cb_nation.addItem(n, n)
        self.cb_nation.currentIndexChanged.connect(self._refresh_filter)
        f.addWidget(self.cb_nation)
        f.addWidget(QtWidgets.QLabel("Ruolo:"))
        self.cb_role = QtWidgets.QComboBox()
        self.cb_role.addItem("(tutti)", None)
        self.cb_role.addItem("V (vicere/capitale)", "V")
        self.cb_role.addItem("G (governatorato)", "G")
        self.cb_role.addItem("normale", "_NONE")
        self.cb_role.currentIndexChanged.connect(self._refresh_filter)
        f.addWidget(self.cb_role)
        lay.addLayout(f)
        self.lst = QtWidgets.QListWidget()
        self.lst.itemDoubleClicked.connect(self._on_accept)
        lay.addWidget(self.lst, 1)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._populate()
        self._refresh_filter()

    def _populate(self):
        self.lst.clear()
        for c in self.store.config["cities"]:
            badges = []
            if c.get("role"): badges.append(c["role"])
            wl = self.store.city_warehouse_level(c["key"])
            if wl > 0: badges.append(f"M{wl}")
            badge_str = (" [" + ",".join(badges) + "]") if badges else ""
            nation = self.store.city_nation(c["key"])
            text = f"{c['id']:>3}  {c['name']}  ·  {nation}{badge_str}"
            it = QtWidgets.QListWidgetItem(text)
            it.setData(QtCore.Qt.UserRole, c["id"])
            self.lst.addItem(it)

    def _refresh_filter(self):
        q = self.ed_search.text().lower().strip()
        nation = self.cb_nation.currentData()
        role = self.cb_role.currentData()
        for i in range(self.lst.count()):
            it = self.lst.item(i)
            cid = it.data(QtCore.Qt.UserRole)
            city = self.store.cities_by_id[cid]
            ok_name = (q == "" or q in city["name"].lower())
            ok_nation = (nation is None or self.store.city_nation(city["key"]) == nation)
            crole = city.get("role")
            if role is None: ok_role = True
            elif role == "_NONE": ok_role = (crole is None)
            else: ok_role = (crole == role)
            it.setHidden(not (ok_name and ok_nation and ok_role))

    def _on_accept(self):
        it = self.lst.currentItem()
        if not it or it.isHidden(): return
        self.selected_city_id = it.data(QtCore.Qt.UserRole)
        self.accept()


# --- Spinbox custom con "MAX" sentinel -------------------------------------

class QtyMaxSpinBox(QtWidgets.QSpinBox):
    """QSpinBox che mostra 'MAX' quando il valore e' 0xFFFF."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(0, QTY_MAX)

    def textFromValue(self, value: int) -> str:
        if value == QTY_MAX:
            return "MAX"
        return str(value)

    def valueFromText(self, text: str) -> int:
        if text.strip().upper() == "MAX":
            return QTY_MAX
        try:
            return int(text)
        except ValueError:
            return 0

    def validate(self, text: str, pos: int):
        if text.strip().upper() in ("", "M", "MA", "MAX"):
            return (QtGui.QValidator.Acceptable, text, pos)
        try:
            n = int(text)
            if 0 <= n <= QTY_MAX:
                return (QtGui.QValidator.Acceptable, text, pos)
        except ValueError:
            pass
        return (QtGui.QValidator.Invalid, text, pos)


class _ModifierToolButton(QtWidgets.QToolButton):
    """ToolButton che emette i modificatori al click."""
    clicked_with_mods = QtCore.Signal(QtCore.Qt.KeyboardModifiers)

    def mouseReleaseEvent(self, ev: QtGui.QMouseEvent) -> None:
        mods = ev.modifiers()
        super().mouseReleaseEvent(ev)
        if self.rect().contains(ev.pos()):
            self.clicked_with_mods.emit(mods)


# --- GoodsTable: tabella editable per le 20 merci di uno stop --------------

class GoodsTable(QtWidgets.QWidget):
    """Tabella inline con tutte le 20 merci editabili in riga."""

    # Segnali per richieste verso il MainWindow:
    advised_price_requested = QtCore.Signal(int, str, str)  # good_id, sides('load'/'unload'/'both'), scope('current'/'all')
    action_changed = QtCore.Signal(int, int)  # good_id, new_action
    trade_changed = QtCore.Signal(int, str, str, int, int)  # good_id, side, mode, qty, price

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

    def __init__(self, store: Store, parent=None):
        super().__init__(parent)
        self.store = store
        self._stop: dict | None = None
        self._route_excluded: list[int] = []
        self._city_has_warehouse = False
        self._city_key: str | None = None
        self._suppress = False
        self._build()

    # Segnali extra per copia/incolla
    copy_good_requested = QtCore.Signal(int)   # good_id
    paste_good_requested = QtCore.Signal(int)  # good_id
    reset_good_requested = QtCore.Signal(int)  # good_id

    def _build(self):
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.table = QtWidgets.QTableWidget(20, self.N_COLS)
        # context menu sulla tabella
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
        h.setSectionResizeMode(self.COL_NAME, QtWidgets.QHeaderView.Interactive)
        h.setSectionResizeMode(self.COL_ACTION, QtWidgets.QHeaderView.Interactive)
        for c in (self.COL_L_MODE, self.COL_L_QTY, self.COL_L_PRICE, self.COL_L_ADV,
                  self.COL_U_MODE, self.COL_U_QTY, self.COL_U_PRICE, self.COL_U_ADV):
            h.setSectionResizeMode(c, QtWidgets.QHeaderView.Interactive)
        self.table.setColumnWidth(self.COL_NAME,     100)
        self.table.setColumnWidth(self.COL_ACTION,   100)
        self.table.setColumnWidth(self.COL_L_MODE,    90)
        self.table.setColumnWidth(self.COL_L_QTY,     80)
        self.table.setColumnWidth(self.COL_L_PRICE,   80)
        self.table.setColumnWidth(self.COL_L_ADV,     80)
        self.table.setColumnWidth(self.COL_U_MODE,    90)
        self.table.setColumnWidth(self.COL_U_QTY,     80)
        self.table.setColumnWidth(self.COL_U_PRICE,   80)
        self.table.setColumnWidth(self.COL_U_ADV,     80)

        # Riferimenti ai widget per riga
        self._row_widgets: list[dict] = []

        for row, g in enumerate(self.store.config["goods"]):
            gid = g["id"]
            # 0: Icon
            it_icon = QtWidgets.QTableWidgetItem(good_icon(gid), "")
            it_icon.setFlags(it_icon.flags() & ~QtCore.Qt.ItemIsEditable)
            self.table.setItem(row, self.COL_ICON, it_icon)
            # 1: Name
            it_name = QtWidgets.QTableWidgetItem(g["name_it"])
            it_name.setFlags(it_name.flags() & ~QtCore.Qt.ItemIsEditable)
            it_name.setData(QtCore.Qt.UserRole, gid)
            self.table.setItem(row, self.COL_NAME, it_name)
            # 2: Action combo
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

                sp_qty = QtyMaxSpinBox()
                sp_qty.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
                sp_qty.setAlignment(QtCore.Qt.AlignRight)
                sp_qty.valueChanged.connect(
                    lambda _v, gid=gid, side=side: self._emit_trade(gid, side))
                self.table.setCellWidget(row, c_qty, sp_qty)

                sp_price = QtWidgets.QSpinBox()
                sp_price.setRange(0, 999_999)
                sp_price.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
                sp_price.setAlignment(QtCore.Qt.AlignRight)
                sp_price.valueChanged.connect(
                    lambda _v, gid=gid, side=side: self._emit_trade(gid, side))
                # Context menu sul prezzo per [Min/Med/Max]
                sp_price.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
                sp_price.customContextMenuRequested.connect(
                    lambda pos, gid=gid, side=side, sp=sp_price:
                        self._show_price_menu(sp, pos, gid, side))
                self.table.setCellWidget(row, c_price, sp_price)

                btn_adv = _ModifierToolButton()
                btn_adv.setText("💰 —")
                btn_adv.setToolTipDuration(0)
                btn_adv.setMinimumWidth(70)
                btn_adv.clicked_with_mods.connect(
                    lambda mods, gid=gid, side=side: self._on_adv_button(gid, side, mods))
                self.table.setCellWidget(row, c_adv, btn_adv)

                row_w[f"{side}_mode"]  = cb_mode
                row_w[f"{side}_qty"]   = sp_qty
                row_w[f"{side}_price"] = sp_price
                row_w[f"{side}_adv"]   = btn_adv
            self._row_widgets.append(row_w)
        self.table.resizeRowsToContents()
        v.addWidget(self.table)
        self.setEnabled(False)

    # --- API publica ----------------------------------------------------

    def set_context(self, stop: dict | None, route_excluded: list[int],
                    city_key: str | None, city_has_warehouse: bool):
        self._stop = stop
        self._route_excluded = list(route_excluded or [])
        self._city_has_warehouse = city_has_warehouse
        self._city_key = city_key
        self.setEnabled(stop is not None)
        self._refresh()

    def _refresh(self):
        """Aggiorna tutti i widget in base a self._stop, senza emettere segnali."""
        self._suppress = True
        try:
            if self._stop is None:
                # Reset visuale
                for row, w in enumerate(self._row_widgets):
                    w["action"].setCurrentIndex(w["action"].findData(ACTION_AUTO))
                    for side in ("load", "unload"):
                        w[f"{side}_mode"].setCurrentIndex(0)
                        w[f"{side}_qty"].setValue(0)
                        w[f"{side}_price"].setValue(0)
                        w[f"{side}_adv"].setText("💰 —")
                        w[f"{side}_adv"].setEnabled(False)
                        self._set_side_enabled(row, side, False)
                return
            stop = self._stop
            for gid in range(20):
                w = self._row_widgets[gid]
                action = stop["actions"][gid]
                w["action"].setCurrentIndex(w["action"].findData(action))
                manual = (action == ACTION_MANUAL)
                # Hint route-excluded: barra il nome
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
                    # Advised button
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
        # price separatamente, dipende anche dal mode

    def _set_row_excluded_style(self, gid: int, excluded: bool):
        name_it = self.table.item(gid, self.COL_NAME)
        if not name_it:
            return
        font = name_it.font()
        font.setStrikeOut(excluded)
        name_it.setFont(font)
        if excluded:
            name_it.setToolTip("Esclusa a livello di rotta")
        else:
            name_it.setToolTip("")

    # --- handlers segnali interni --------------------------------------

    def _on_action_combo(self, good_id: int):
        if self._suppress: return
        cb = self._row_widgets[good_id]["action"]
        new_action = cb.currentData()
        self.action_changed.emit(good_id, new_action)

    def _emit_trade(self, good_id: int, side: str):
        if self._suppress or self._stop is None: return
        if self._stop["actions"][good_id] != ACTION_MANUAL:
            return
        w = self._row_widgets[good_id]
        mode = w[f"{side}_mode"].currentData()
        qty = w[f"{side}_qty"].value()
        price = w[f"{side}_price"].value()
        self.trade_changed.emit(good_id, side, mode, qty, price)

    def _on_adv_button(self, good_id: int, side: str, mods: QtCore.Qt.KeyboardModifiers):
        if self._stop is None: return
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
        if row < 0 or row >= 20:
            return
        gid = row
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


# --- Finestra principale ----------------------------------------------------

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, store: Store):
        super().__init__()
        self.store = store
        self.route = Route(store)
        self._wire_route()
        self.setWindowTitle(self._title())
        self.resize(1380, 820)
        self._build_menu()
        self._build_central()
        self._build_statusbar()
        self._on_route_changed()

    def _wire_route(self):
        self.route.changed.connect(self._on_route_changed)
        self.route.stop_changed.connect(self._on_stop_internally_changed)

    def _title(self) -> str:
        return f"{APP_NAME} — {self.route.display_name()}"

    def _build_menu(self):
        mb = self.menuBar()
        m_file = mb.addMenu("&File")
        for label, key, slot in [
            ("Nuova rotta", QtGui.QKeySequence.New, self._on_new_route),
            ("Apri rotta...", QtGui.QKeySequence.Open, self._on_open_route),
        ]:
            a = m_file.addAction(label); a.setShortcut(key); a.triggered.connect(slot)
        m_file.addSeparator()
        a = m_file.addAction("Salva"); a.setShortcut(QtGui.QKeySequence.Save); a.triggered.connect(self._on_save_route)
        a = m_file.addAction("Salva con nome..."); a.setShortcut(QtGui.QKeySequence.SaveAs); a.triggered.connect(self._on_save_route_as)
        m_file.addSeparator()
        a = m_file.addAction("Esci"); a.setShortcut(QtGui.QKeySequence.Quit); a.triggered.connect(self.close)

        m_edit = mb.addMenu("&Modifica")
        m_edit.addAction("Copia").setShortcut(QtGui.QKeySequence.Copy)
        m_edit.addAction("Incolla").setShortcut(QtGui.QKeySequence.Paste)

        m_tools = mb.addMenu("&Strumenti")
        m_tools.addAction("Gestisci città (magazzini, nazioni)...").triggered.connect(self._on_manage_cities)

        m_help = mb.addMenu("&Aiuto")
        m_help.addAction("Informazioni").triggered.connect(self._on_about)

    def _build_central(self):
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        # --- sinistra: stop + esclusioni --------------
        left = QtWidgets.QWidget()
        lv = QtWidgets.QVBoxLayout(left)
        lv.addWidget(QtWidgets.QLabel("Stop della rotta"))
        self.stops_list = QtWidgets.QListWidget()
        self.stops_list.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.stops_list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.stops_list.model().rowsMoved.connect(self._on_stops_reordered)
        self.stops_list.itemSelectionChanged.connect(self._on_stop_selected)
        self.stops_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.stops_list.customContextMenuRequested.connect(self._on_stop_context_menu)
        lv.addWidget(self.stops_list, 1)
        h = QtWidgets.QHBoxLayout()
        b_add = QtWidgets.QPushButton("+ Tappa"); b_add.clicked.connect(self._on_add_stop)
        b_rem = QtWidgets.QPushButton("− Rimuovi"); b_rem.clicked.connect(self._on_remove_stop)
        h.addWidget(b_add); h.addWidget(b_rem)
        lv.addLayout(h)
        lv.addWidget(QtWidgets.QLabel("Esclusioni globali"))
        self.route_excl_list = QtWidgets.QListWidget()
        self.route_excl_list.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        for g in self.store.config["goods"]:
            it = QtWidgets.QListWidgetItem(good_icon(g["id"]), g["name_it"])
            it.setFlags(it.flags() | QtCore.Qt.ItemIsUserCheckable)
            it.setCheckState(QtCore.Qt.Unchecked)
            it.setData(QtCore.Qt.UserRole, g["id"])
            self.route_excl_list.addItem(it)
        self.route_excl_list.itemChanged.connect(self._on_route_excl_changed)
        lv.addWidget(self.route_excl_list, 1)

        # --- destra: header citta + tabella merci ----------
        right = QtWidgets.QWidget()
        rv = QtWidgets.QVBoxLayout(right)
        # Header strip con info citta
        self.stop_header = QtWidgets.QLabel("(nessuno stop selezionato)")
        self.stop_header.setStyleSheet("font-size:14pt; font-weight:bold;")
        rv.addWidget(self.stop_header)
        self.stop_meta = QtWidgets.QLabel("")
        self.stop_meta.setTextFormat(QtCore.Qt.RichText)
        self.stop_meta.setWordWrap(True)
        rv.addWidget(self.stop_meta)
        sep = QtWidgets.QFrame(); sep.setFrameShape(QtWidgets.QFrame.HLine); rv.addWidget(sep)
        # Hint per i bottoni 💰
        hint = QtWidgets.QLabel(
            "<i>💰 prezzo consigliato &nbsp;•&nbsp; "
            "Click: solo questa merce+lato &nbsp;•&nbsp; "
            "Ctrl+Click: carica+scarica &nbsp;•&nbsp; "
            "Shift+Click: tutte le manuali &nbsp;•&nbsp; "
            "click destro sul prezzo: scelta Min/Mercato/Max</i>"
        )
        hint.setTextFormat(QtCore.Qt.RichText)
        hint.setWordWrap(True)
        rv.addWidget(hint)
        # Tabella merci
        self.goods_table = GoodsTable(self.store)
        self.goods_table.action_changed.connect(self._on_action_changed)
        self.goods_table.trade_changed.connect(self._on_trade_changed)
        self.goods_table.advised_price_requested.connect(self._on_advised_price_requested)
        self.goods_table.copy_good_requested.connect(self._on_copy_good)
        self.goods_table.paste_good_requested.connect(self._on_paste_good)
        self.goods_table.reset_good_requested.connect(self._on_reset_good)
        # clipboard interno (separato dalla clipboard di sistema)
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
            f"{self.route.display_name()} • {n}/{ahr.MAX_STOPS} stop • "
            f"{excl} merci escluse • user_state: {ovs} override"
        )

    # --- helpers --------------------------------------------------------

    def _current_stop_idx(self) -> int | None:
        i = self.stops_list.currentRow()
        if 0 <= i < len(self.route.stops): return i
        return None

    # --- aggiornamenti UI ----------------------------------------------

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

        # esclusioni globali
        was = self.route_excl_list.blockSignals(True)
        try:
            excl = set(self.route.excluded_route)
            for i in range(self.route_excl_list.count()):
                it = self.route_excl_list.item(i)
                gid = it.data(QtCore.Qt.UserRole)
                it.setCheckState(QtCore.Qt.Checked if gid in excl else QtCore.Qt.Unchecked)
        finally:
            self.route_excl_list.blockSignals(was)
        # ricarica tabella anche per riflettere il route_excluded (strikethrough)
        idx = self._current_stop_idx()
        if idx is not None:
            self._refresh_table_for_stop(idx)
        self.setWindowTitle(self._title())
        self._refresh_status()

    def _on_stop_internally_changed(self, stop_idx: int):
        if stop_idx == self._current_stop_idx():
            self._refresh_table_for_stop(stop_idx)
        self.setWindowTitle(self._title())
        self._refresh_status()

    def _on_stop_selected(self):
        idx = self._current_stop_idx()
        self._update_stop_panel(idx)
        self._refresh_table_for_stop(idx)

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
            self.stop_header.setText("(nessuno stop selezionato)")
            self.stop_meta.setText("")
            return
        stop = self.route.stops[idx]
        cid = stop["trailer"]["city_id"]
        city = self.store.cities_by_id.get(cid)
        if not city:
            self.stop_header.setText(f"city#{cid} (sconosciuta)"); self.stop_meta.setText(""); return
        is_start = bool(stop["trailer"]["start_flag"])
        self.stop_header.setText(f"{idx + 1}. {city['name']}" + (" ★ (partenza)" if is_start else ""))
        role = city.get("role") or "—"
        nation = self.store.city_nation(city["key"])
        wlvl = self.store.city_warehouse_level(city["key"])
        wh = (f"livello {wlvl} ({wlvl * 800} t)" if wlvl > 0 else "no")
        prod_ids = city.get("produces", [])
        prod_names = ", ".join(self.store.goods_by_id[g]["name_it"] for g in prod_ids)
        self.stop_meta.setText(
            f"<b>id città:</b> {cid} &nbsp; "
            f"<b>nazione corrente:</b> {nation} &nbsp; "
            f"<b>ruolo:</b> {role} &nbsp; "
            f"<b>magazzino:</b> {wh}<br>"
            f"<b>produce:</b> {prod_names}"
        )

    # --- segnali dalla tabella verso Route ------------------------------

    def _on_action_changed(self, good_id: int, new_action: int):
        idx = self._current_stop_idx()
        if idx is None: return
        self.route.set_good_action(idx, good_id, new_action)

    def _on_trade_changed(self, good_id: int, side: str, mode: str, qty: int, price: int):
        idx = self._current_stop_idx()
        if idx is None: return
        self.route.set_good_trade(idx, good_id, side=side, mode=mode, qty=qty, price=price)

    def _on_advised_price_requested(self, good_id: int, sides: str, scope: str):
        idx = self._current_stop_idx()
        if idx is None: return
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
                    skipped += 1; continue
                t = stop["trades"][gid]
                mode = t[f"{side}_mode"]; qty = t[f"{side}_qty"]
                if mode == "warehouse":
                    mode = "city"
                self.route.set_good_trade(idx, gid, side=side, mode=mode, qty=qty, price=adv)
                applied += 1
        if applied:
            scope_lbl = f"tutte ({len(target_gids)})" if scope == "all" else "1 merce"
            side_lbl = "carico+scarico" if sides == "both" else ("carico" if sides == "load" else "scarico")
            self.statusBar().showMessage(
                f"Applicato prezzo consigliato a {scope_lbl}, lato {side_lbl}: {applied} valori modificati"
                + (f" ({skipped} senza consigliato)" if skipped else ""),
                4000,
            )

    # --- copia/incolla ---------------------------------------------------

    def _on_copy_good(self, good_id: int):
        idx = self._current_stop_idx()
        if idx is None: return
        stop = self.route.stops[idx]
        import copy
        self._good_clipboard = {
            "action": stop["actions"][good_id],
            "trade": copy.deepcopy(stop["trades"][good_id]),
        }
        gname = self.store.goods_by_id[good_id]["name_it"]
        self.statusBar().showMessage(f"Copiato '{gname}' negli appunti", 3000)

    def _on_paste_good(self, good_id: int):
        if not self._good_clipboard:
            QtWidgets.QMessageBox.information(self, "Incolla", "Nessuna configurazione merce negli appunti.")
            return
        idx = self._current_stop_idx()
        if idx is None: return
        stop = self.route.stops[idx]
        src = self._good_clipboard
        # Applica l'azione (resetta i trade se non manuale)
        self.route.set_good_action(idx, good_id, src["action"])
        if src["action"] == ACTION_MANUAL:
            # Applica i trade del clipboard mantenendo i campi corretti
            for side in ("load", "unload"):
                mode = src["trade"][f"{side}_mode"]
                qty = src["trade"][f"{side}_qty"]
                price_raw = src["trade"][f"{side}_price"]
                if mode == "warehouse":
                    price = 0  # set_good_trade decoder rimette il sentinel
                else:
                    price = price_raw if price_raw != WAREHOUSE_PRICE else 0
                self.route.set_good_trade(idx, good_id, side=side, mode=mode, qty=qty, price=price)
        gname = self.store.goods_by_id[good_id]["name_it"]
        self.statusBar().showMessage(f"Configurazione incollata su '{gname}'", 3000)

    def _on_reset_good(self, good_id: int):
        idx = self._current_stop_idx()
        if idx is None: return
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
        a_copy = menu.addAction(f"Copia configurazione di tutto lo stop '{name}'")
        a_paste = menu.addAction(f"Incolla configurazione su '{name}'")
        menu.addSeparator()
        a_rem = menu.addAction(f"Rimuovi tappa '{name}'")
        chosen = menu.exec(self.stops_list.viewport().mapToGlobal(pos))
        if chosen == a_copy:
            self._copy_stop(row)
        elif chosen == a_paste:
            self._paste_stop(row)
        elif chosen == a_rem:
            self.route.remove_stop(row)

    def _copy_stop(self, idx: int):
        import copy
        stop = self.route.stops[idx]
        self._stop_clipboard = {
            "display_order": list(stop["display_order"]),
            "actions": list(stop["actions"]),
            "trades": copy.deepcopy(stop["trades"]),
        }
        city = self.store.cities_by_id.get(stop["trailer"]["city_id"])
        name = city["name"] if city else "?"
        self.statusBar().showMessage(f"Copiato tutto lo stop '{name}' negli appunti", 3000)

    def _paste_stop(self, idx: int):
        if not self._stop_clipboard:
            QtWidgets.QMessageBox.information(self, "Incolla", "Nessuna configurazione stop negli appunti.")
            return
        if not (0 <= idx < len(self.route.stops)): return
        stop = self.route.stops[idx]
        src = self._stop_clipboard
        # NON tocchiamo il trailer (citta, start_flag) — solo le impostazioni merci
        stop["display_order"] = list(src["display_order"])
        stop["actions"] = list(src["actions"])
        import copy
        stop["trades"] = copy.deepcopy(src["trades"])
        # rispetta action_kinds derivati
        stop["action_kinds"] = [ahr.ACTION_NAMES.get(a, "?") for a in stop["actions"]]
        self.route.set_dirty()
        self.route.stop_changed.emit(idx)
        city = self.store.cities_by_id.get(stop["trailer"]["city_id"])
        name = city["name"] if city else "?"
        self.statusBar().showMessage(f"Configurazione incollata su stop '{name}'", 3000)

    def _on_route_excl_changed(self, item: QtWidgets.QListWidgetItem):
        excl = []
        for i in range(self.route_excl_list.count()):
            it = self.route_excl_list.item(i)
            if it.checkState() == QtCore.Qt.Checked:
                excl.append(it.data(QtCore.Qt.UserRole))
        self.route.set_excluded_route(excl)

    def _on_stops_reordered(self, *args):
        new_ids = [self.stops_list.item(i).data(QtCore.Qt.UserRole) for i in range(self.stops_list.count())]
        if len(new_ids) != len(self.route.stops): return
        new_stops, used = [], set()
        for cid in new_ids:
            for j, s in enumerate(self.route.stops):
                if j in used: continue
                if s["trailer"]["city_id"] == cid:
                    new_stops.append(s); used.add(j); break
        if len(new_stops) == len(self.route.stops):
            self.route.doc["stops"] = new_stops
            self.route._recompute_start_flags()
            self.route.set_dirty()
            self.route.changed.emit()

    # --- azioni menu ----------------------------------------------------

    def _maybe_discard_unsaved(self) -> bool:
        if not self.route.dirty: return True
        r = QtWidgets.QMessageBox.question(
            self, "Modifiche non salvate",
            "La rotta corrente ha modifiche non salvate. Vuoi salvarla prima?",
            QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Cancel,
            QtWidgets.QMessageBox.Save,
        )
        if r == QtWidgets.QMessageBox.Save: return self._on_save_route()
        return r == QtWidgets.QMessageBox.Discard

    def _on_new_route(self):
        if not self._maybe_discard_unsaved(): return
        self.route = Route(self.store); self._wire_route(); self._on_route_changed()

    def _on_open_route(self):
        if not self._maybe_discard_unsaved(): return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Apri rotta", str(ROUTES_DIR), "File .ahr (*.ahr)")
        if not path: return
        try:
            self.route = Route.from_file(self.store, Path(path)); self._wire_route()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Errore apertura", f"{type(e).__name__}: {e}"); return
        self._on_route_changed()

    def _on_save_route(self) -> bool:
        if not self.route.stops:
            QtWidgets.QMessageBox.warning(self, "Salva", "Non puoi salvare una rotta senza stop."); return False
        if not self.route.filepath:
            return self._on_save_route_as()
        try:
            self.route.save_to(self.route.filepath)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Errore salvataggio", f"{type(e).__name__}: {e}"); return False
        self._on_route_changed(); return True

    def _on_save_route_as(self) -> bool:
        if not self.route.stops:
            QtWidgets.QMessageBox.warning(self, "Salva con nome", "Non puoi salvare una rotta senza stop."); return False
        default_dir = ROUTES_DIR / "built"; default_dir.mkdir(parents=True, exist_ok=True)
        suggested = str(default_dir / "rotta.ahr")
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Salva rotta con nome", suggested, "File .ahr (*.ahr)")
        if not path: return False
        try:
            self.route.save_to(Path(path))
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Errore salvataggio", f"{type(e).__name__}: {e}"); return False
        self._on_route_changed(); return True

    def _on_add_stop(self):
        if len(self.route.stops) >= ahr.MAX_STOPS:
            QtWidgets.QMessageBox.warning(self, "Aggiungi tappa", f"Massimo {ahr.MAX_STOPS} stop per rotta."); return
        dlg = AddStopDialog(self.store, self)
        if dlg.exec() != QtWidgets.QDialog.Accepted or dlg.selected_city_id is None: return
        try:
            idx = self.route.add_stop(dlg.selected_city_id)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Errore", str(e)); return
        self.stops_list.setCurrentRow(idx)

    def _on_remove_stop(self):
        idx = self.stops_list.currentRow()
        if idx < 0: return
        self.route.remove_stop(idx)

    def _on_manage_cities(self):
        QtWidgets.QMessageBox.information(self, "Gestisci città", "TODO F5")

    def _on_about(self):
        QtWidgets.QMessageBox.about(
            self, "Informazioni",
            f"<h3>{APP_NAME}</h3><p>Versione {APP_VERSION}</p>"
            "<p>Editor per le rotte commerciali (.ahr) di Port Royale 2 — Impero & Pirati.</p>"
        )

    def closeEvent(self, ev: QtGui.QCloseEvent):
        if self._maybe_discard_unsaved(): ev.accept()
        else: ev.ignore()


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    store = Store()
    win = MainWindow(store)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
