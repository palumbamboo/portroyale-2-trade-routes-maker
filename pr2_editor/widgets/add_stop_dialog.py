"""Dialog "Aggiungi tappa": selezione città dalla lista filtrabile."""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ..store import Store


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
            if c.get("role"):
                badges.append(c["role"])
            wl = self.store.city_warehouse_level(c["key"])
            if wl > 0:
                badges.append(f"M{wl}")
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
            if role is None:
                ok_role = True
            elif role == "_NONE":
                ok_role = (crole is None)
            else:
                ok_role = (crole == role)
            it.setHidden(not (ok_name and ok_nation and ok_role))

    def _on_accept(self):
        it = self.lst.currentItem()
        if not it or it.isHidden():
            return
        self.selected_city_id = it.data(QtCore.Qt.UserRole)
        self.accept()
