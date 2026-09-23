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

# Реальные шапки (подтверждены публичными первоисточниками, RESEARCH_BANK_STATEMENT_SAMPLES.md):
SBER_EMAIL_HEADER = ("Тип карты;Номер карты;Дата совершения операции;Дата обработки операции;"
                     "Код авторизации;Тип операции;Город совершения операции;Страна совершения операции;"
                     "Описание;Валюта операции;Сумма в валюте операции;Сумма в валюте счета")
TINKOFF_REAL_HEADER = ("Дата операции;Дата платежа;Номер карты;Статус;Сумма операции;Валюта операции;"
                       "Сумма платежа;Валюта платежа;Кэшбэк;Категория;MCC;Описание;Бонусы (включая кэшбэк)")


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


def gen_sber_email(n: int = 8, seed: int = 7) -> str:
    """Сбер email-CSV («выписка на e-mail как Excel-лист»): реальная 12-колоночная шапка, `;`, utf-8.

    Суммы — в «Сумма в валюте счета» (у физлиц счёт рублёвый), «Валюта операции» пустая;
    edge-case `-,01` (вторая строка). Статуса в этом формате нет.
    """
    lines = [SBER_EMAIL_HEADER]
    for i, (d, m, kop, _status) in enumerate(_base_rows(n, seed)):
        code = 200000 + i
        amount = "-0,01" if i == 1 else fmt_ru(kop)
        lines.append(f"Основная;*6833;{d.strftime('%d.%m.%Y')};{d.strftime('%d.%m.%Y')};{code};"
                     f"4829;MOSCOW;RUS;{m};;;{amount};")
    return "\n".join(lines) + "\n"


def gen_tinkoff_real(n: int = 10, seed: int = 3, encoding: str | None = None) -> str | bytes:
    """Т-Банк: реальная 13-колоночная шапка (MCC/Кэшбэк/Бонусы), `Статус=OK` у проведённых,
    пустая «Дата платежа» у третьей строки, «В обработке» — не проведена (адаптер пропускает).
    """
    lines = [TINKOFF_REAL_HEADER]
    for i, (d, m, kop, status) in enumerate(_base_rows(n, seed)):
        dt = f"{d.strftime('%d.%m.%Y')} {9 + i % 12:02d}:{i % 60:02d}:00"
        pay_dt = "" if i == 2 else d.strftime("%d.%m.%Y")
        t_status = "OK" if status == "Выполнено" else status
        lines.append(f"{dt};{pay_dt};*8305;{t_status};{fmt_ru(kop)};RUB;{fmt_ru(kop)};RUB;"
                     f"0;Прочее;5411;{m};0")
    raw = "\r\n".join(lines) + "\r\n"
    return raw.encode("cp1251") if encoding == "cp1251" else raw
