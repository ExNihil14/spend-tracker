from __future__ import annotations

import random
from decimal import InvalidOperation

import pytest

from spendtrack.store import (
    MAX_AMOUNT_KOPECKS,
    fmt_amount,
    fmt_amount_signed,
    parse_amount,
)


def test_fmt_amount_stays_ascii_for_machine_output():
    """Машинная форма (CSV/промпты/CLI): ASCII-минус, без плюса у положительных."""
    assert fmt_amount(-12345) == "-123.45"
    assert fmt_amount(12345) == "123.45"
    assert fmt_amount(0) == "0.00"


def test_fmt_amount_signed_display_form():
    """Отображаемая форма: явный знак, типографский минус U+2212 (WCAG 1.4.1)."""
    assert fmt_amount_signed(-12345) == "−123.45"
    assert fmt_amount_signed(12345) == "+123.45"
    assert fmt_amount_signed(0) == "0.00"
    assert fmt_amount_signed(-5) == "−0.05"


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
    assert parse_amount("1 234.56") == 123456     # NBSP как разделитель тысяч
    assert parse_amount("−123,45") == -12345      # U+2212 (минус из выписок)
    assert parse_amount("–123,45") == -12345      # en-dash
    assert parse_amount("+1 234,56") == 123456         # явный плюс
    assert parse_amount("1,2345") == 123               # >2 знаков → HALF_UP до копеек
    assert parse_amount("1,2355") == 124
    assert parse_amount("0,01") == 1
    assert parse_amount(" 5000 ") == 500000
    assert parse_amount(5000) == 500000                # int — уже рубли


def test_parse_amount_rounding_is_half_up():
    """HALF_UP, а не HALF_EVEN (адъюдикация wave8, tests_money S1).

    Прежние примеры `1,2345`/`1,2355` НЕ являются точной половиной копейки, поэтому
    HALF_UP и HALF_EVEN давали бы одинаковый ответ. Здесь — ровно половина.
    """
    assert parse_amount("0,005") == 1          # HALF_EVEN дал бы 0
    assert parse_amount("-0,005") == -1        # HALF_EVEN дал бы 0
    assert parse_amount("1,225") == 123        # HALF_EVEN дал бы 122
    assert parse_amount("-1,225") == -123
    assert parse_amount("0,015") == 2          # ровно половина, HALF_UP вверх
    assert parse_amount("0,025") == 3          # HALF_EVEN дал бы 2
    assert type(parse_amount("0,005")) is int


def test_parse_amount_returns_int_not_float():
    """Копейки — целые: `123.0 == 123`, поэтому одного равенства мало (S1)."""
    for kop in (123, -123, 0, 1_000_000):
        got = parse_amount(fmt_amount(kop))
        assert got == kop
        assert type(got) is int, f"{kop}: тип {type(got).__name__}, а нужен int"


def test_amount_precision_at_enforced_limit():
    """Граница КОНТРАКТА: точность копеек до предела `MAX_AMOUNT_KOPECKS` (10^11 = 10^9 ₽).

    Замер (адъюдикация wave8): `fmt_amount` делит на 100 через двоичный float, поэтому точность
    теряется выше ~2^53 копеек (≈9.007×10^13 ₽) — это примерно в 9×10^4 раз выше принудительного
    лимита, то есть недостижимо через API и CSV-импорт. Контракт, который здесь закрепляем:
    «в пределах лимита сумма не теряет копейки». Границу 2^53 сознательно НЕ фиксируем как
    поддерживаемую (иначе пришлось бы форматировать целыми, а не float).
    """
    for kop in (MAX_AMOUNT_KOPECKS, -MAX_AMOUNT_KOPECKS, MAX_AMOUNT_KOPECKS - 1,
                MAX_AMOUNT_KOPECKS // 2):
        shown = fmt_amount(kop)
        assert parse_amount(shown) == kop, f"{kop}: показано {shown!r} и не разобралось обратно"


def test_parse_amount_rejects_garbage():
    with pytest.raises(InvalidOperation):
        parse_amount("abc")
    with pytest.raises(InvalidOperation):
        parse_amount("")


def test_parse_amount_rejects_non_finite():
    """«nan»/«inf» Decimal принимает, но это не деньги: контролируемая InvalidOperation (§G)."""
    for bad in ("nan", "NaN", "inf", "-Infinity", "sNaN"):
        with pytest.raises(InvalidOperation):
            parse_amount(bad)


def test_delta_words_expense_direction():
    """Дельта расходов словами (M-5): рост трат — ↑, снижение — ↓, ноль — без изменений."""
    from spendtrack.store import delta_words

    assert delta_words(-692500) == "↑ на 6 925,00 ₽"
    assert delta_words(692500) == "↓ на 6 925,00 ₽"
    assert delta_words(0) == "без изменений"
