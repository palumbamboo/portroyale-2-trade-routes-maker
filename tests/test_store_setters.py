"""Store setters: write, read, cleanup of empty overrides."""
from __future__ import annotations


def test_warehouse_set_and_read(store):
    assert store.city_warehouse_level("corpus_christi") == 0
    store.set_city_warehouse_level("corpus_christi", 3)
    assert store.city_warehouse_level("corpus_christi") == 3
    assert store.city_has_warehouse("corpus_christi")


def test_warehouse_cleanup_on_zero(store):
    store.set_city_warehouse_level("corpus_christi", 3)
    assert "corpus_christi" in store.user_state["city_overrides"]
    store.set_city_warehouse_level("corpus_christi", 0)
    assert "corpus_christi" not in store.user_state["city_overrides"]


def test_nation_default_returned_when_no_override(store):
    # Port Royale has "spain" as default in config
    assert store.city_nation("port_royale") == "spain"


def test_nation_override_and_cleanup_to_default(store):
    store.set_city_nation("port_royale", "france")
    assert store.city_nation("port_royale") == "france"
    # Going back to the default should clear the override
    store.set_city_nation("port_royale", "spain")
    assert "port_royale" not in store.user_state["city_overrides"]
    assert store.city_nation("port_royale") == "spain"


def test_nation_set_none_clears_override(store):
    store.set_city_nation("port_royale", "france")
    store.set_city_nation("port_royale", None)
    assert "port_royale" not in store.user_state["city_overrides"]


def test_advised_price_override_and_clear(store):
    default_buy = store.city_advised_price("corpus_christi", 0, "buy")
    store.set_city_advised_price("corpus_christi", 0, "buy", 99)
    assert store.city_advised_price("corpus_christi", 0, "buy") == 99
    sell_def = store.city_advised_price("corpus_christi", 0, "sell")
    assert sell_def == store.goods_by_id[0].get("price_sell_advised", 0)
    store.set_city_advised_price("corpus_christi", 0, "buy", None)
    assert store.city_advised_price("corpus_christi", 0, "buy") == default_buy
    assert "corpus_christi" not in store.user_state["city_overrides"]


def test_multiple_overrides_independent(store):
    store.set_city_warehouse_level("corpus_christi", 2)
    store.set_city_nation("port_royale", "france")
    store.set_city_advised_price("corpus_christi", 11, "sell", 200)
    overrides = store.user_state["city_overrides"]
    assert overrides["corpus_christi"]["warehouse_level"] == 2
    assert overrides["corpus_christi"]["advised_prices"]["11"]["sell"] == 200
    assert overrides["port_royale"]["nation"] == "france"
    store.set_city_warehouse_level("corpus_christi", 0)
    assert "warehouse_level" not in overrides["corpus_christi"]
    assert overrides["corpus_christi"]["advised_prices"]["11"]["sell"] == 200


def test_persistence_across_instances(store, tmp_path):
    from pr2_editor.store import Store
    store.set_city_warehouse_level("corpus_christi", 5)
    store.set_city_nation("port_royale", "france")
    other = Store(user_state_path=store._user_state_path)
    assert other.city_warehouse_level("corpus_christi") == 5
    assert other.city_nation("port_royale") == "france"


def test_user_state_changed_signal_emitted(store):
    received: list[int] = []
    store.user_state_changed.connect(lambda: received.append(1))
    store.set_city_warehouse_level("corpus_christi", 1)
    store.set_city_nation("port_royale", "france")
    assert len(received) == 2
