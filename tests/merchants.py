"""Словарь реалистичных мерчантов РФ → ожидаемые категории (для теста правил).

Только названия брендов и типовых формулировок (без PII). Используется
`test_rules_accuracy.py`, чтобы измерять покрытие keyword-правил taxonomy.toml.
"""
from __future__ import annotations

MERCHANTS: dict[str, str] = {
    # groceries
    "ЛЕНТА": "groceries",
    "МАГНИТ": "groceries",
    "ПЯТЁРОЧКА": "groceries",
    "ПЯТЕРОЧКА": "groceries",
    "АШАН": "groceries",
    "ВКУСВИЛЛ": "groceries",
    "ВКУС ВИЛЛ": "groceries",
    # fuel
    "ЛУКОЙЛ": "fuel",
    "ТАТНЕФТЬ": "fuel",
    "РОСНЕФТЬ": "fuel",
    "ГАЗПРОМНЕФТЬ": "fuel",
    # transport
    "ЯНДЕКС GO": "transport",
    "ЯНДЕКС ТАКСИ": "transport",
    "UBER": "transport",
    "МЕТРО": "transport",
    # subscriptions
    "NETFLIX": "subscriptions",
    "SPOTIFY": "subscriptions",
    "YOUTUBE PREMIUM": "subscriptions",
    "KINOPOISK": "subscriptions",
    "ИВИ": "subscriptions",
    # household
    "ОЗОН": "household",
    "WILDBERRIES": "household",
    # transfers / income
    "ПЕРЕВОД": "transfers",
    "ВОЗВРАТ": "transfers",
    "ЗАРАБОТНАЯ ПЛАТА": "income",
    "ЗАРПЛАТА": "income",
    "SALARY": "income",
}
