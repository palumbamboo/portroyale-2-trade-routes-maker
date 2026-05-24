"""ahr decoder/encoder: byte-equality sul fixture esistente."""
from __future__ import annotations
from pathlib import Path

import ahr

FIXTURE = Path(__file__).resolve().parents[1] / "rotte" / "test" / "fixture_rotta01.ahr"


def test_fixture_exists():
    assert FIXTURE.exists(), f"fixture mancante: {FIXTURE}"


def test_roundtrip_byte_equality():
    original = FIXTURE.read_bytes()
    doc = ahr.decode(original)
    encoded = ahr.encode(doc)
    assert encoded == original, "encode(decode(x)) != x"
