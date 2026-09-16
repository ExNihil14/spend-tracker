from __future__ import annotations

import random
from decimal import InvalidOperation

import pytest

from spendtrack.store import fmt_amount, parse_amount


def test_parse_amount_roundtrip_random():
    """Property: parse_amount(fmt_amount(k)) == k для случайных сумм (seed фиксирован)."""
    rng = random.Random(42)
    for _ in range(500):
        kop = rng.randint(-10_000_000, 10_000_000)
        assert parse_amount(fmt_amount(kop)) == kop


def test_parse_amount_real_world_variants():
    assert parse_amount("-1 234,56") == -123456
    assert parse_amount("1\u00a0234.56") == 123456     # NBSP как разделитель тысяч
    assert parse_amount("\u2212123,45") == -12345      # U+2212 (минус из выписок)
    assert parse_amount("\u2013123,45") == -12345      # en-dash
    assert parse_amount("+1 234,56") == 123456         # явный плюс
    assert parse_amount("1,2345") == 123               # >2 знаков → HALF_UP до копеек
    assert parse_amount("1,2355") == 124
    assert parse_amount("0,01") == 1
    assert parse_amount(" 5000 ") == 500000
    assert parse_amount(5000) == 500000                # int — уже рубли


def test_parse_amount_rejects_garbage():
    with pytest.raises(InvalidOperation):
        parse_amount("abc")
    with pytest.raises(InvalidOperation):
        parse_amount("")
