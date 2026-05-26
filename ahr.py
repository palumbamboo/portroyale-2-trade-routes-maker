"""Decoder/encoder/builder for the .ahr (Port Royale 2 — Autoroute) file format.

Usage:
    python ahr.py decode "file.ahr" "file.json"
    python ahr.py encode "file.json" "file.ahr"     # raw JSON (output of decode) -> .ahr
    python ahr.py build  <spec.json> "file.ahr"     # user-friendly JSON -> .ahr
    python ahr.py roundtrip "file.ahr"              # verify decode->encode equality
    python ahr.py cities "file.ahr"
    python ahr.py decode-dir <in_dir> <out_dir>
    python ahr.py test <dir>                        # roundtrip every .ahr in dir

.ahr layout (reverse-engineered):
- Header (11 bytes):
    magic[4]   = b'A\\x04\\x00\\x00'
    nstops[1]  : actual stop count
    capacity[1]: ceil(nstops/4)*4, capped at 16
    bitmap[5]  : route-wide exclusion bitmap (bit set = good active, clear = excluded)
                 byte 0 = goods 0-7, byte 1 = 8-15, byte 2 = 16-19 + 4 spare bits

- Stop (426 bytes, one per stop):
    display_order[20] : permutation 0..19 (UI order; manual goods on top)
    actions[20] u32 LE: 0=excluded, 1=auto, 2=manual
    trades[20] (16 bytes each):
        load_price  u32 LE (= 0xFFFFFFFF when "from warehouse", else gold/ton threshold)
        load_qty    u16 LE (= 0xFFFF for "max", 0 = nothing)
        load_aux    u16 LE (snapshot/residue, not a user input — kept for roundtrip)
        unload_price u32 LE
        unload_qty  u16 LE
        unload_aux  u16 LE
    trailer (6 bytes):
        city_id, 0x00, 0x21, 0x00, start_flag, 0x00
"""
from __future__ import annotations
import json
import struct
import sys
from pathlib import Path

# Format constants
HEADER_SIZE = 0x0B
STOP_SIZE = 0x1AA       # 426 bytes
MAX_STOPS = 16
N_GOODS = 20
TRADE_OFFSET = 0x64
TRAILER_OFFSET = 0x1A4

MAGIC = b'A\x04\x00\x00'


def _capacity(nstops: int) -> int:
    """Header byte 5 (observed): smallest multiple of 4 >= nstops, capped at 16."""
    cap = ((nstops + 3) // 4) * 4
    return min(cap, MAX_STOPS)

# Good names (verified on georgetown-test.ahr: the order matches the in-game UI).
# P.R.2 has 20 transportable goods: 19 commercial + 1 special (Settlers, id 19).
# Kept as informational labels in the decoded JSON; the canonical identifier is
# the numeric good_id (0..19). pr2_config.json maps id -> {key, name_it, name_en}.
GOOD_NAMES = [
    "grano", "frutta", "legno", "mattoni", "mais",
    "zucchero", "cotone", "canapa", "carne", "vestiti",
    "corda", "rum", "caffe", "cacao", "tinture",
    "tabacco", "spezie", "vino", "attrezzi", "coloni",
]


def decode(data: bytes) -> dict:
    if data[:4] != MAGIC:
        raise ValueError(f"Unexpected magic: {data[:4].hex()}")
    nstops = data[4]
    expected = HEADER_SIZE + nstops * STOP_SIZE
    if len(data) != expected:
        raise ValueError(
            f"Unexpected size: {len(data)} bytes (expected {expected} for {nstops} stops)"
        )
    if nstops > MAX_STOPS:
        raise ValueError(f"nstops={nstops} > {MAX_STOPS}")

    # Header bytes 6-10 = route-wide exclusion bitmap (1=good active on route, 0=excluded)
    # bits[0..7]  = goods 0..7  (byte 6)
    # bits[8..15] = goods 8..15 (byte 7)
    # bits[16..19] = goods 16..19 (byte 8 lower nibble)
    bitmap_bytes = data[6:11]
    excluded_goods = []
    for g in range(N_GOODS):
        byte_i, bit_i = divmod(g, 8)
        if not (bitmap_bytes[byte_i] >> bit_i) & 1:
            excluded_goods.append(g)
    # Residual bytes (10) and residual bits (>= 20): kept raw for now.
    header = {
        "nstops": data[4],
        "capacity": data[5],   # = ceil(nstops/4)*4, capped at 16 — derived in encode
        "route_excluded_goods": excluded_goods,
        "_bitmap_raw": bitmap_bytes.hex(),  # preserved for lossless roundtrip
    }

    stops = []
    for i in range(nstops):
        off = HEADER_SIZE + i * STOP_SIZE
        blk = data[off:off + STOP_SIZE]
        stops.append(_decode_stop(blk))

    return {"_format": "ahr-v1", "header": header, "stops": stops}


ACTION_NAMES = {0: "excluded", 1: "auto", 2: "manual"}


def _decode_stop(blk: bytes) -> dict:
    perm = list(blk[0:N_GOODS])
    actions = list(struct.unpack(f'<{N_GOODS}I', blk[N_GOODS:N_GOODS + 4 * N_GOODS]))
    action_kinds = [ACTION_NAMES.get(a, f"unknown_{a}") for a in actions]
    trades = []
    for g in range(N_GOODS):
        rec = blk[TRADE_OFFSET + 16 * g:TRADE_OFFSET + 16 * (g + 1)]
        # Half A = LOAD settings, Half B = UNLOAD settings.
        # Verified across georgetown + min-max-price + avg-price + warehouse-test:
        # - load_price/unload_price (u32 LE): PRICE THRESHOLD vs the city's price.
        #   If = 0xFFFFFFFF ("WAREHOUSE_SENTINEL") the trade uses the WAREHOUSE
        #   (no threshold).
        # - load_qty/unload_qty (u16 LE): quantity (0xFFFF = "max" sentinel, 0 = nothing).
        # - load_aux/unload_aux (u16 LE): snapshot residue, NOT a user input.
        #   Preserved for a lossless roundtrip.
        load_price, load_qty, load_aux = struct.unpack('<IHH', rec[0:8])
        unload_price, unload_qty, unload_aux = struct.unpack('<IHH', rec[8:16])
        load_mode = "warehouse" if load_price == 0xFFFFFFFF else "city"
        unload_mode = "warehouse" if unload_price == 0xFFFFFFFF else "city"
        trades.append({
            "good": GOOD_NAMES[g] if g < len(GOOD_NAMES) else f"good_{g}",
            "load_mode": load_mode,
            "load_price": load_price,
            "load_qty": load_qty,
            "load_aux": load_aux,
            "unload_mode": unload_mode,
            "unload_price": unload_price,
            "unload_qty": unload_qty,
            "unload_aux": unload_aux,
        })
    trailer_raw = blk[TRAILER_OFFSET:TRAILER_OFFSET + 6]
    trailer = {
        "city_id": trailer_raw[0],
        "const_b1": trailer_raw[1],
        "marker": trailer_raw[2],
        "const_b3": trailer_raw[3],
        "start_flag": trailer_raw[4],
        "const_b5": trailer_raw[5],
    }
    return {
        "display_order": perm,
        "actions": actions,
        "action_kinds": action_kinds,
        "trades": trades,
        "trailer": trailer,
    }


def encode(doc: dict) -> bytes:
    h = doc["header"]
    nstops = len(doc["stops"])
    # Allow explicit override (header.nstops); default to the length of stops.
    nstops = h.get("nstops", nstops)
    capacity = h.get("capacity", _capacity(nstops))
    # Build the exclusion bitmap: prefer route_excluded_goods, fall back to _bitmap_raw.
    if "route_excluded_goods" in h:
        excluded = set(h["route_excluded_goods"])
        bitmap = bytearray(b'\xff' * 5)
        for g in range(N_GOODS):
            if g in excluded:
                byte_i, bit_i = divmod(g, 8)
                bitmap[byte_i] &= ~(1 << bit_i) & 0xff
        bitmap_bytes = bytes(bitmap)
    else:
        bitmap_bytes = bytes.fromhex(h.get("_bitmap_raw", "ffffffffff"))
    out = bytearray()
    out += MAGIC
    out += bytes([nstops, capacity])
    out += bitmap_bytes
    assert len(out) == HEADER_SIZE, f"header size {len(out)} != {HEADER_SIZE}"

    for stop in doc["stops"]:
        out += _encode_stop(stop)

    return bytes(out)


def _encode_stop(s: dict) -> bytes:
    blk = bytearray(STOP_SIZE)
    perm = s["display_order"]
    assert len(perm) == N_GOODS
    blk[0:N_GOODS] = bytes(perm)
    actions = s["actions"]
    assert len(actions) == N_GOODS
    struct.pack_into(f'<{N_GOODS}I', blk, N_GOODS, *actions)
    for g, t in enumerate(s["trades"]):
        struct.pack_into('<IHH', blk, TRADE_OFFSET + 16 * g,
                         t["load_price"], t["load_qty"], t["load_aux"])
        struct.pack_into('<IHH', blk, TRADE_OFFSET + 16 * g + 8,
                         t["unload_price"], t["unload_qty"], t["unload_aux"])
    tr = s["trailer"]
    blk[TRAILER_OFFSET + 0] = tr["city_id"]
    blk[TRAILER_OFFSET + 1] = tr["const_b1"]
    blk[TRAILER_OFFSET + 2] = tr["marker"]
    blk[TRAILER_OFFSET + 3] = tr["const_b3"]
    blk[TRAILER_OFFSET + 4] = tr["start_flag"]
    blk[TRAILER_OFFSET + 5] = tr["const_b5"]
    return bytes(blk)


## ------- Builder: user-friendly spec -> .ahr ----------------------------

WAREHOUSE_PRICE = 0xFFFFFFFF
QTY_MAX = 0xFFFF


class BuildError(ValueError):
    """Validation error raised from build_route()."""


def _qty(v, field: str) -> int:
    if v is None or v == 0 or v == "":
        return 0
    if isinstance(v, str) and v.lower() == "max":
        return QTY_MAX
    if isinstance(v, int):
        if not (0 <= v <= QTY_MAX):
            raise BuildError(f"{field}: qty {v} out of range [0,{QTY_MAX}]; use 'max' for the sentinel")
        return v
    raise BuildError(f"{field}: qty must be int or 'max', not {v!r}")


def _half(side: dict | None, field: str) -> tuple[int, int, int]:
    """Return (price_u32, qty_u16, aux_u16) for one half (load or unload)."""
    if not side:
        return (0, 0, 0)
    mode = side.get("mode", "city")
    if mode not in ("city", "warehouse"):
        raise BuildError(f"{field}.mode must be 'city' or 'warehouse', not {mode!r}")
    qty = _qty(side.get("qty"), field)
    if mode == "warehouse":
        if "price" in side and side["price"] not in (None, 0):
            raise BuildError(f"{field}: 'price' is not allowed with mode=warehouse")
        return (WAREHOUSE_PRICE, qty, 0)
    price = side.get("price", 0) or 0
    if not isinstance(price, int) or price < 0 or price > 0xFFFFFFFE:
        raise BuildError(f"{field}.price must be int [0..2^32-2], not {price!r}")
    return (price, qty, 0)


def _good_id_map(cfg: dict) -> dict[str, int]:
    return {g["key"]: g["id"] for g in cfg["goods"]}


def _city_id_map(cfg: dict) -> dict[str, int]:
    return {c["key"]: c["id"] for c in cfg["cities"] if c.get("id") is not None}


def build_route(spec: dict, cfg: dict) -> bytes:
    """Build a binary .ahr starting from a user-friendly spec + pr2_config.json."""
    g_id = _good_id_map(cfg)
    c_id = _city_id_map(cfg)

    # --- global exclusions (header bitmap) ---
    excluded_route_keys = spec.get("excluded_route", [])
    excluded_route_ids = []
    for k in excluded_route_keys:
        if k not in g_id:
            raise BuildError(f"excluded_route: unknown good '{k}'")
        excluded_route_ids.append(g_id[k])

    stops_spec = spec.get("stops", [])
    if not stops_spec:
        raise BuildError("no stops in the spec ('stops' is empty)")
    if len(stops_spec) > MAX_STOPS:
        raise BuildError(f"too many stops ({len(stops_spec)}, max {MAX_STOPS})")

    # --- build the "raw" document and reuse encode() ---
    raw_stops = []
    for idx, s in enumerate(stops_spec):
        city_key = s.get("city")
        if city_key not in c_id:
            raise BuildError(f"stop #{idx}: unknown city '{city_key}'")
        excluded_here_ids = []
        for k in s.get("excluded_here", []):
            if k not in g_id:
                raise BuildError(f"stop #{idx} ({city_key}).excluded_here: unknown good '{k}'")
            excluded_here_ids.append(g_id[k])
        manual_specs = s.get("manual", {}) or {}
        manual_ids: dict[int, dict] = {}
        for k, v in manual_specs.items():
            if k not in g_id:
                raise BuildError(f"stop #{idx} ({city_key}).manual: unknown good '{k}'")
            manual_ids[g_id[k]] = v

        # per-good actions
        actions = []
        all_excluded = set(excluded_route_ids) | set(excluded_here_ids)
        for gid in range(N_GOODS):
            if gid in manual_ids:
                actions.append(2)
            elif gid in all_excluded:
                actions.append(0)
            else:
                actions.append(1)

        # display_order: manuals in id-order, then everything else in id-order
        manuals_sorted = sorted(manual_ids.keys())
        rest = [g for g in range(N_GOODS) if g not in manual_ids]
        display_order = manuals_sorted + rest
        assert len(display_order) == N_GOODS

        # per-good trades
        trades = []
        for gid in range(N_GOODS):
            good_name = (cfg["goods"][gid]["key"]
                         if gid < len(cfg["goods"]) else f"good_{gid}")
            if gid in manual_ids:
                m = manual_ids[gid]
                load_p, load_q, load_a = _half(m.get("load"),
                                               f"stop#{idx}.{city_key}.{good_name}.load")
                unload_p, unload_q, unload_a = _half(m.get("unload"),
                                                    f"stop#{idx}.{city_key}.{good_name}.unload")
            else:
                load_p = load_q = load_a = 0
                unload_p = unload_q = unload_a = 0
            trades.append({
                "good": good_name,
                "load_mode": "warehouse" if load_p == WAREHOUSE_PRICE else "city",
                "load_price": load_p,
                "load_qty": load_q,
                "load_aux": load_a,
                "unload_mode": "warehouse" if unload_p == WAREHOUSE_PRICE else "city",
                "unload_price": unload_p,
                "unload_qty": unload_q,
                "unload_aux": unload_a,
            })

        raw_stops.append({
            "display_order": display_order,
            "actions": actions,
            "action_kinds": [ACTION_NAMES[a] for a in actions],
            "trades": trades,
            "trailer": {
                "city_id": c_id[city_key],
                "const_b1": 0x00,
                "marker":   0x21,
                "const_b3": 0x00,
                "start_flag": 1 if idx == 0 else 0,
                "const_b5": 0x00,
            },
        })

    doc = {
        "_format": "ahr-v1",
        "header": {
            "nstops": len(raw_stops),
            "capacity": _capacity(len(raw_stops)),
            "route_excluded_goods": sorted(excluded_route_ids),
        },
        "stops": raw_stops,
    }
    return encode(doc)


def _cmd_build(spec_path: Path, out_path: Path) -> None:
    cfg_path = _find_config()
    if not cfg_path.exists():
        print(f"ERR: pr2_config.json not found ({cfg_path})")
        sys.exit(2)
    cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
    spec = json.loads(spec_path.read_text(encoding='utf-8'))
    try:
        data = build_route(spec, cfg)
    except BuildError as e:
        print(f"ERR build: {e}")
        sys.exit(1)
    out_path.write_bytes(data)
    print(f"OK: {spec_path.name} -> {out_path.name} ({len(data)} bytes, {len(spec.get('stops', []))} stops)")


def _cmd_decode(src: Path, dst: Path) -> None:
    data = src.read_bytes()
    doc = decode(data)
    dst.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"OK: {src} -> {dst} ({len(data)} bytes, {len(doc['stops'])} stops)")


def _cmd_encode(src: Path, dst: Path) -> None:
    doc = json.loads(src.read_text(encoding='utf-8'))
    data = encode(doc)
    dst.write_bytes(data)
    print(f"OK: {src} -> {dst} ({len(data)} bytes)")


def _load_city_index(config_path: Path) -> dict[int, dict]:
    """Load pr2_config.json and return {city_id: city_record} (only cities with non-null id)."""
    if not config_path.exists():
        return {}
    cfg = json.loads(config_path.read_text(encoding='utf-8'))
    out = {}
    for c in cfg.get("cities", []):
        if c.get("id") is not None:
            out[c["id"]] = c
    return out


def _find_config() -> Path:
    """Search for pr2_config.json: first next to this script, then walking up."""
    candidates = [Path(__file__).parent / "pr2_config.json"]
    cur = Path.cwd()
    for _ in range(4):
        candidates.append(cur / "pr2_config.json")
        cur = cur.parent
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]  # default for the "not found" message


def _cmd_cities(src: Path) -> None:
    raw = src.read_bytes()
    doc = decode(raw)
    cfg_path = _find_config()
    by_id = _load_city_index(cfg_path)
    if cfg_path.exists():
        cfg_note = f"(config: {cfg_path.name}, {len(by_id)} cities mapped)"
    else:
        cfg_note = "(no pr2_config.json found next to the file)"
    print(f"{src.name}  {cfg_note}")
    print(f"{'#':>2}  {'city_id':>8}  start  {'name':<24}  nation")
    print("-" * 60)
    for i, st in enumerate(doc["stops"]):
        cid = st["trailer"]["city_id"]
        start = "*" if st["trailer"]["start_flag"] else " "
        info = by_id.get(cid)
        name = info["name"] if info else "?"
        nation = info.get("nation", "?") if info else "?"
        print(f"{i:>2}  0x{cid:02x}({cid:>3})  {start:<5}  {name:<24}  {nation}")


def _cmd_decode_dir(in_dir: Path, out_dir: Path) -> None:
    if not in_dir.is_dir():
        print(f"ERR: {in_dir} is not a directory")
        sys.exit(2)
    out_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(in_dir.glob("*.ahr"))
    if not files:
        print(f"No .ahr in {in_dir}")
        return
    for src in files:
        dst = out_dir / (src.stem + ".json")
        data = src.read_bytes()
        doc = decode(data)
        dst.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f"  {src.name} -> {dst.name}")
    print(f"OK: {len(files)} files decoded to {out_dir}")


def _cmd_test(root: Path) -> None:
    if not root.is_dir():
        print(f"ERR: {root} is not a directory")
        sys.exit(2)
    files = sorted(root.glob("*.ahr"))
    if not files:
        print(f"No .ahr in {root}")
        return
    failed = 0
    for src in files:
        raw = src.read_bytes()
        try:
            doc = decode(raw)
            again = encode(doc)
            if raw == again:
                print(f"  OK    {src.name}  ({len(raw)} bytes)")
            else:
                failed += 1
                for i, (a, b) in enumerate(zip(raw, again)):
                    if a != b:
                        print(f"  FAIL  {src.name}  first diff @0x{i:04X}: {a:02x}!={b:02x}")
                        break
                else:
                    print(f"  FAIL  {src.name}  length orig={len(raw)} enc={len(again)}")
        except Exception as e:
            failed += 1
            print(f"  ERR   {src.name}  {type(e).__name__}: {e}")
    print(f"\n{len(files)-failed}/{len(files)} OK" + (" — failures present" if failed else ""))
    if failed:
        sys.exit(1)


def _cmd_roundtrip(src: Path) -> None:
    raw = src.read_bytes()
    doc = decode(raw)
    again = encode(doc)
    if raw == again:
        print(f"OK roundtrip identical ({len(raw)} bytes)")
    else:
        # Find the first divergent byte
        for i, (a, b) in enumerate(zip(raw, again)):
            if a != b:
                print(f"DIVERGE @0x{i:04X}: orig=0x{a:02x} encoded=0x{b:02x}")
                break
        else:
            print(f"DIVERGE length: orig={len(raw)} encoded={len(again)}")
        sys.exit(1)


def main(argv: list[str]) -> None:
    if len(argv) < 2:
        print(__doc__)
        sys.exit(2)
    cmd = argv[1]
    if cmd == "decode" and len(argv) == 4:
        _cmd_decode(Path(argv[2]), Path(argv[3]))
    elif cmd == "encode" and len(argv) == 4:
        _cmd_encode(Path(argv[2]), Path(argv[3]))
    elif cmd == "roundtrip" and len(argv) == 3:
        _cmd_roundtrip(Path(argv[2]))
    elif cmd == "cities" and len(argv) == 3:
        _cmd_cities(Path(argv[2]))
    elif cmd == "build" and len(argv) == 4:
        _cmd_build(Path(argv[2]), Path(argv[3]))
    elif cmd == "decode-dir" and len(argv) == 4:
        _cmd_decode_dir(Path(argv[2]), Path(argv[3]))
    elif cmd == "test" and len(argv) == 3:
        _cmd_test(Path(argv[2]))
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main(sys.argv)
