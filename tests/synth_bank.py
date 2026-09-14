"""Детерминированный генератор синтетических банковских выписок для тестов Import.

Только синтетика (без PII): реальные форматы колонок, edge-cases
(статус «В обработке», дубль покупки в один день, доход/возврат).
"""
from __future__ import annotations

import random
from datetime import date, timedelta

MERCHANTS = ["ЛЕНТА", "МАГНИТ", "ПЯТЁРОЧКА", "ЛУКОЙЛ", "ЯНДЕКС GO", "NETFLIX", "ОЗОН", "АПТЕКА РУ"]

SBER_HEADER = ("Номер документа;Дата операции;Дата платежа;Номер карты;Статус;Сумма операции;"
               "Валюта операции;Сумма платежа;Валюта платежа;Категория;Описание")
TINKOFF_HEADER = "Дата;Сумма операции;Категория;Описание;Счёт"
YANDEX_HEADER = "datetime;operation;amount;currency;category;title;merchant;description"


def fmt_ru(kopecks: int) -> str:
    """-12345 → '-123,45'; -123456789 → '-1 234 567,89' (формат Сбера: пробел + запятая)."""
    s = f"{abs(kopecks) / 100:.2f}"
    int_part, dec = s.split(".")
    groups = []
    while len(int_part) > 3:
        groups.insert(0, int_part[-3:])
        int_part = int_part[:-3]
    groups.insert(0, int_part)
    sign = "-" if kopecks < 0 else ""
    return f"{sign}{' '.join(groups)},{dec}"


def _base_rows(n: int, seed: int) -> list[tuple[date, str, int, str]]:
    """(date, merchant, kopecks, status): расходы + доход + возврат + дубль + «В обработке»."""
    rng = random.Random(seed)
    d0 = date(2026, 9, 1)
    rows: list[tuple[date, str, int, str]] = []
    for i in range(n):
        d = d0 + timedelta(days=i // 3)
        m = rng.choice(MERCHANTS)
        kop = -max(1000, min(500_000, int(rng.lognormvariate(6.8, 1.0))))
        rows.append((d, m, kop, "Выполнено"))
    rows.append((d0 + timedelta(days=5), "ЗАРАБОТНАЯ ПЛАТА", 25_000_000, "Выполнено"))
    rows.append((d0 + timedelta(days=7), "ВОЗВРАТ OZON", 129_000, "Выполнено"))
    rows.append(rows[2])  # легитимный дубль в один день
    rows.append((d0 + timedelta(days=9), "МАГНИТ", -77_700, "В обработке"))  # должна быть пропущена
    return rows


def gen_sber(n: int = 20, seed: int = 42, encoding: str | None = None) -> str | bytes:
    lines = [SBER_HEADER]
    for i, (d, m, kop, status) in enumerate(_base_rows(n, seed), start=1):
        dt = f"{d.strftime('%d.%m.%Y')} {8 + i % 12:02d}:00"
        cat = "Прочее"
        lines.append(f"{i};{dt};{d.strftime('%d.%m.%Y')};1234;{status};{fmt_ru(kop)};RUB;"
                     f"{fmt_ru(kop)};RUB;{cat};{m}")
    raw = "\r\n".join(lines) + "\r\n"
    return raw.encode("cp1251") if encoding == "cp1251" else raw


def gen_tinkoff(n: int = 10, seed: int = 1, encoding: str | None = None) -> str | bytes:
    lines = [TINKOFF_HEADER]
    for d, m, kop, _status in _base_rows(n, seed)[:-1]:  # без статусной строки (нет колонки)
        lines.append(f"{d.strftime('%d.%m.%Y')};{fmt_ru(kop)};Прочее;{m};40817810000000000000")
    raw = "\n".join(lines) + "\n"
    return raw.encode("cp1251") if encoding == "cp1251" else raw


def gen_yandex(n: int = 8, seed: int = 2) -> str:
    lines = [YANDEX_HEADER]
    for d, m, kop, _status in _base_rows(n, seed)[:-1]:
        lines.append(f"{d.isoformat()}T10:00:00;payment;{kop / 100:.2f};RUB;Прочее;{m};{m};{m}")
    return "\n".join(lines) + "\n"
