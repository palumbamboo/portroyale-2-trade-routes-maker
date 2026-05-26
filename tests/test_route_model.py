"""Route model: add/remove/move stop, start_flag, display_order, excluded goods."""
from __future__ import annotations

import ahr
from pr2_editor.constants import ACTION_AUTO, ACTION_EXCLUDED, ACTION_MANUAL
from pr2_editor.route import Route


def test_empty_route_has_no_stops(store):
    r = Route(store)
    assert r.stops == []
    assert r.doc["header"]["nstops"] == 0
    assert not r.dirty


def test_add_stop_sets_start_flag_only_on_first(store):
    r = Route(store)
    r.add_stop(0)
    r.add_stop(1)
    r.add_stop(2)
    flags = [s["trailer"]["start_flag"] for s in r.stops]
    assert flags == [1, 0, 0]
    assert r.doc["header"]["nstops"] == 3
    assert r.doc["header"]["capacity"] == ahr._capacity(3)
    assert r.dirty


def test_remove_first_stop_recomputes_start_flag(store):
    r = Route(store)
    r.add_stop(0); r.add_stop(1); r.add_stop(2)
    r.remove_stop(0)
    assert len(r.stops) == 2
    assert r.stops[0]["trailer"]["start_flag"] == 1
    assert r.stops[1]["trailer"]["start_flag"] == 0


def test_move_stop_reassigns_start_flag(store):
    r = Route(store)
    r.add_stop(0); r.add_stop(1); r.add_stop(2)
    r.move_stop(0, 2)
    # Lo stop in posizione 0 ora deve avere start_flag=1
    assert r.stops[0]["trailer"]["start_flag"] == 1
    assert r.stops[2]["trailer"]["start_flag"] == 0


def test_set_good_action_to_manual_prefills_minmax(store):
    r = Route(store)
    r.add_stop(0)
    r.set_good_action(0, 5, ACTION_MANUAL)
    stop = r.stops[0]
    assert stop["actions"][5] == ACTION_MANUAL
    # manuali in cima al display_order
    assert stop["display_order"][0] == 5
    # default prices: buy = price_min, sell = price_max (sensible starting thresholds)
    good_5 = store.goods_by_id[5]
    assert stop["trades"][5]["load_price"] == int(good_5["price_min"])
    assert stop["trades"][5]["unload_price"] == int(good_5["price_max"])
    # qty deliberately stays at 0 — the user picks the volume
    assert stop["trades"][5]["load_qty"] == 0
    assert stop["trades"][5]["unload_qty"] == 0


def test_set_good_action_to_excluded_resets_trades(store):
    r = Route(store)
    r.add_stop(0)
    r.set_good_action(0, 5, ACTION_MANUAL)
    r.set_good_trade(0, 5, side="load", mode="city", qty=100, price=50)
    assert r.stops[0]["trades"][5]["load_qty"] == 100
    # Tornare a EXCLUDED deve azzerare i trade
    r.set_good_action(0, 5, ACTION_EXCLUDED)
    t = r.stops[0]["trades"][5]
    assert t["load_qty"] == 0 and t["load_price"] == 0
    assert t["load_mode"] == "city"


def test_excluded_route_sorted_unique(store):
    r = Route(store)
    r.set_excluded_route([3, 1, 3, 5, 1])
    assert r.excluded_route == [1, 3, 5]


def test_dirty_flag_lifecycle(store):
    r = Route(store)
    assert not r.dirty
    r.add_stop(0)
    assert r.dirty
    r.set_dirty(False)
    assert not r.dirty
