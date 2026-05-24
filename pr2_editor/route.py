"""Route: modello della rotta corrente (wrapper attorno al dict serializzabile)."""
from __future__ import annotations
from pathlib import Path

from PySide6 import QtCore

import ahr

from .constants import ACTION_AUTO, ACTION_MANUAL, QTY_MAX, WAREHOUSE_PRICE
from .store import Store


class Route(QtCore.QObject):
    changed = QtCore.Signal()
    stop_changed = QtCore.Signal(int)

    def __init__(
        self, store: Store, doc: dict | None = None, filepath: Path | None = None
    ):
        super().__init__()
        self.store = store
        self.doc = doc if doc else self._empty_doc()
        self.filepath = filepath
        self._dirty = False

    @staticmethod
    def _empty_doc() -> dict:
        return {
            "_format": "ahr-v1",
            "header": {"nstops": 0, "capacity": 0, "route_excluded_goods": []},
            "stops": [],
        }

    @staticmethod
    def _empty_stop(city_id: int, is_start: bool) -> dict:
        return {
            "display_order": list(range(20)),
            "actions": [ACTION_AUTO] * 20,
            "action_kinds": ["auto"] * 20,
            "trades": [
                {
                    "good": ahr.GOOD_NAMES[g],
                    "load_mode": "city", "load_price": 0, "load_qty": 0, "load_aux": 0,
                    "unload_mode": "city", "unload_price": 0, "unload_qty": 0, "unload_aux": 0,
                }
                for g in range(20)
            ],
            "trailer": {
                "city_id": city_id, "const_b1": 0x00, "marker": 0x21, "const_b3": 0x00,
                "start_flag": 1 if is_start else 0, "const_b5": 0x00,
            },
        }

    @property
    def dirty(self) -> bool:
        return self._dirty

    def set_dirty(self, v: bool = True) -> None:
        if self._dirty != v:
            self._dirty = v
            self.changed.emit()

    @property
    def stops(self) -> list[dict]:
        return self.doc["stops"]

    @property
    def excluded_route(self) -> list[int]:
        return list(self.doc["header"].get("route_excluded_goods", []))

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
        if not (0 <= stop_idx < len(self.stops)) or not (0 <= good_id < 20):
            return
        stop = self.stops[stop_idx]
        if stop["actions"][good_id] == new_action:
            return
        stop["actions"][good_id] = new_action
        stop["action_kinds"][good_id] = ahr.ACTION_NAMES.get(new_action, "?")
        if new_action != ACTION_MANUAL:
            t = stop["trades"][good_id]
            t["load_mode"] = "city"; t["load_price"] = 0; t["load_qty"] = 0; t["load_aux"] = 0
            t["unload_mode"] = "city"; t["unload_price"] = 0; t["unload_qty"] = 0; t["unload_aux"] = 0
        self._rebuild_display_order(stop_idx)
        self.set_dirty()
        self.stop_changed.emit(stop_idx)

    def _rebuild_display_order(self, stop_idx: int) -> None:
        stop = self.stops[stop_idx]
        manuals = [g for g in range(20) if stop["actions"][g] == ACTION_MANUAL]
        rest = [g for g in range(20) if stop["actions"][g] != ACTION_MANUAL]
        stop["display_order"] = manuals + rest

    def set_good_trade(
        self, stop_idx: int, good_id: int, *, side: str, mode: str, qty: int, price: int
    ) -> None:
        if side not in ("load", "unload") or mode not in ("city", "warehouse"):
            return
        if not (0 <= stop_idx < len(self.stops)) or not (0 <= good_id < 20):
            return
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
