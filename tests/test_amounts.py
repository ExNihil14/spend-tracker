from __future__ import annotations

import random
from decimal import InvalidOperation

import pytest

from spendtrack.store import fmt_amount, fmt_amount_signed, parse_amount


def test_fmt_amount_stays_ascii_for_machine_output():
    """Машинная форма (CSV/промпты/CLI): ASCII-минус, без плюса у положительных."""
    assert fmt_amount(-12345) == "-123.45"
    assert fmt_amount(12345) == "123.45"
    assert fmt_amount(0) == "0.00"


def test_fmt_amount_signed_display_form():
    """Отображаемая форма: явный знак, типографский минус U+2212 (WCAG 1.4.1)."""
    assert fmt_amount_signed(-12345) == "\u2212123.45"
    assert fmt_amount_signed(12345) == "+123.45"
    assert fmt_amount_signed(0) == "0.00"
    assert fmt_amount_signed(-5) == "\u22120.05"


def test_fmt_amount_signed_roundtrip_parse():
    """Отображаемую форму можно скормить обратно parse_amount (U+2212/«+» — читаются)."""
    for kop in (-123456, 123456, 1, -1, 0):
        assert parse_amount(fmt_amount_signed(kop)) == kop


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


def test_delta_words_expense_direction():
    """Дельта расходов словами (M-5): рост трат — ↑, снижение — ↓, ноль — без изменений."""
    from spendtrack.store import delta_words

    assert delta_words(-692500) == "↑ на 6\u00a0925,00 ₽"
    assert delta_words(692500) == "↓ на 6\u00a0925,00 ₽"
    assert delta_words(0) == "без изменений"
