"""Реестр кодов и строк ошибок (W2 ресёрча ошибок): один источник до i18n.

Коды стабильны — тесты/логи опираются на них, а не на текст; при вводе i18n строки переезжают
в `config/locales/` через `t()` (DESIGN_I18N_LEGAL_A11Y.md), коды остаются.
"""
from __future__ import annotations

ERRORS: dict[str, str] = {
    "db_busy": "База данных занята или недоступна — повторите через несколько секунд",
    "internal": "Внутренняя ошибка — подробности в логе приложения",
    "amount_unrecognized": "сумма не распознана",
    "goal_amount_unrecognized": "сумма цели не распознана",
    "not_a_number": "не число: {value!r}",
}


def text(code: str, **fmt: object) -> str:
    """Строка по коду; неизвестный код — программная ошибка (KeyError), не пользовательская."""
    return ERRORS[code].format(**fmt)
