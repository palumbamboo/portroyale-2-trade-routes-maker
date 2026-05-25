"""Store: static config + user_state (per-game overrides) persisted to disk."""
from __future__ import annotations
import json
from pathlib import Path

from PySide6 import QtCore

from .constants import CONFIG_PATH, USER_STATE_PATH


class Store(QtCore.QObject):
    user_state_changed = QtCore.Signal()

    def __init__(
        self,
        parent: QtCore.QObject | None = None,
        *,
        config_path: Path | None = None,
        user_state_path: Path | None = None,
    ):
        super().__init__(parent)
        self._config_path = Path(config_path) if config_path else CONFIG_PATH
        self._user_state_path = Path(user_state_path) if user_state_path else USER_STATE_PATH
        if not self._config_path.exists():
            raise FileNotFoundError(f"pr2_config.json not found at {self._config_path}")
        self.config = json.loads(self._config_path.read_text(encoding="utf-8"))
        assert len(self.config["goods"]) == 20
        assert len(self.config["cities"]) == 60
        self.user_state = self._load_user_state()
        self.cities_by_id = {c["id"]: c for c in self.config["cities"]}
        self.cities_by_key = {c["key"]: c for c in self.config["cities"]}
        self.goods_by_id = {g["id"]: g for g in self.config["goods"]}
        self.goods_by_key = {g["key"]: g for g in self.config["goods"]}

    def _load_user_state(self) -> dict:
        if self._user_state_path.exists():
            return json.loads(self._user_state_path.read_text(encoding="utf-8"))
        state = {"_format": "pr2-user-state-v1", "city_overrides": {}}
        self._user_state_path.write_text(
            json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return state

    def save_user_state(self) -> None:
        self._user_state_path.write_text(
            json.dumps(self.user_state, indent=2, ensure_ascii=False), encoding="utf-8"
        )
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

    def set_city_advised_price(
        self, city_key: str, good_id: int, side: str, value: int | None
    ) -> None:
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

    def set_city_warehouse_level(self, city_key: str, level: int) -> None:
        ov = self.user_state["city_overrides"].setdefault(city_key, {})
        if level <= 0:
            ov.pop("warehouse_level", None)
        else:
            ov["warehouse_level"] = int(level)
        if not ov:
            self.user_state["city_overrides"].pop(city_key, None)
        self.save_user_state()

    def set_city_nation(self, city_key: str, nation: str | None) -> None:
        ov = self.user_state["city_overrides"].setdefault(city_key, {})
        default_nation = self.cities_by_key[city_key]["nation"]
        if not nation or nation == default_nation:
            ov.pop("nation", None)
        else:
            ov["nation"] = nation
        if not ov:
            self.user_state["city_overrides"].pop(city_key, None)
        self.save_user_state()
