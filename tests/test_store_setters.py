"""Setter di Store: scrittura, lettura, cleanup degli override vuoti."""
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
    # Port Royale ha "spagna" come default nel config
    assert store.city_nation("port_royale") == "spagna"


def test_nation_override_and_cleanup_to_default(store):
    store.set_city_nation("port_royale", "francia")
    assert store.city_nation("port_royale") == "francia"
    # Tornare al default deve pulire l'override
    store.set_city_nation("port_royale", "spagna")
    assert "port_royale" not in store.user_state["city_overrides"]
    assert store.city_nation("port_royale") == "spagna"


def test_nation_set_none_clears_override(store):
    store.set_city_nation("port_royale", "francia")
    store.set_city_nation("port_royale", None)
    assert "port_royale" not in store.user_state["city_overrides"]


def test_advised_price_override_and_clear(store):
    # Buy default per Grano (gid=0) viene dal config
    default_buy = store.city_advised_price("corpus_christi", 0, "buy")
    store.set_city_advised_price("corpus_christi", 0, "buy", 99)
    assert store.city_advised_price("corpus_christi", 0, "buy") == 99
    # Sell non e' toccato
    sell_def = store.city_advised_price("corpus_christi", 0, "sell")
    assert sell_def == store.goods_by_id[0].get("price_sell_advised", 0)
    # Reset: rimuove buy ma se sell non esiste -> pulisce tutto
    store.set_city_advised_price("corpus_christi", 0, "buy", None)
    assert store.city_advised_price("corpus_christi", 0, "buy") == default_buy
    assert "corpus_christi" not in store.user_state["city_overrides"]


def test_multiple_overrides_independent(store):
    store.set_city_warehouse_level("corpus_christi", 2)
    store.set_city_nation("port_royale", "francia")
    store.set_city_advised_price("corpus_christi", 11, "sell", 200)
    overrides = store.user_state["city_overrides"]
    assert overrides["corpus_christi"]["warehouse_level"] == 2
    assert overrides["corpus_christi"]["advised_prices"]["11"]["sell"] == 200
    assert overrides["port_royale"]["nation"] == "francia"
    # Rimuovere uno non tocca gli altri
    store.set_city_warehouse_level("corpus_christi", 0)
    assert "warehouse_level" not in overrides["corpus_christi"]
    assert overrides["corpus_christi"]["advised_prices"]["11"]["sell"] == 200


def test_persistence_across_instances(store, tmp_path):
    from pr2_editor.store import Store
    store.set_city_warehouse_level("corpus_christi", 5)
    store.set_city_nation("port_royale", "francia")
    # Una seconda istanza che punta allo stesso file deve vedere lo stato salvato
    other = Store(user_state_path=store._user_state_path)
    assert other.city_warehouse_level("corpus_christi") == 5
    assert other.city_nation("port_royale") == "francia"


def test_user_state_changed_signal_emitted(store):
    received: list[int] = []
    store.user_state_changed.connect(lambda: received.append(1))
    store.set_city_warehouse_level("corpus_christi", 1)
    store.set_city_nation("port_royale", "francia")
    assert len(received) == 2
