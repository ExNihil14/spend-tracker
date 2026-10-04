"""W2 ресёрча ошибок: реестр кодов/строк (единый источник до i18n через t())."""
from __future__ import annotations

from decimal import InvalidOperation

import pytest

from spendtrack import errors
from spendtrack.store import parse_amount


def test_registry_has_core_codes_and_formats():
    assert {"db_busy", "internal", "amount_unrecognized", "not_a_number"} <= set(errors.ERRORS)
    assert errors.text("not_a_number", value="abc") == "не число: 'abc'"
    with pytest.raises(KeyError):
        errors.text("no_such_code")


def test_parse_amount_uses_registry():
    with pytest.raises(InvalidOperation) as e:
        parse_amount("nan")  # «nan» — ветка не-числа (Decimal-мусор вроде «abc» падает своим сообщением)
    assert str(e.value) == errors.text("not_a_number", value="nan")
