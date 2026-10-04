"""Цели/копилки (schema v7, research 03.10): «виртуальный конверт» — goal + append-only взносы.

Тесты — на публичный интерфейс Store (usage-first): как цель создаётся, как копится, что
хранилище отвергает. Схема (STRICT/CHECK/FK) проверяется вторым рубежом — прямым SQL
(мимо Python-валидации всё равно не пройдёт).
"""
from __future__ import annotations

import sqlite3

import pytest

from spendtrack.store import _TX_DDL, MAX_AMOUNT_KOPECKS, SCHEMA_VERSION, Store


def test_add_goal_validates_and_returns_id(store):
    gid = store.add_goal("Отпуск", 150_000_00, due_month="2027-06")
    assert isinstance(gid, int) and gid > 0
    [goal] = store.list_goals()
    assert goal["title"] == "Отпуск"
    assert goal["target_kopecks"] == 150_000_00
    assert goal["currency"] == "RUB"
    assert goal["due_month"] == "2027-06"
    assert goal["created_month"] and len(goal["created_month"]) == 7
    assert goal["archived"] == 0

    for title, target, currency, due_month in (
        ("   ", 100_00, "RUB", None),       # пустое название
        ("Цель", 0, "RUB", None),           # нулевая сумма
        ("Цель", -5, "RUB", None),          # отрицательная сумма
        ("Цель", 100_00, "руб", None),      # не ISO-код
        ("Цель", 100_00, "RUB", "2027-13"), # месяц 13
        ("Цель", 100_00, "RUB", "27-06"),   # не ГГГГ-ММ
    ):
        with pytest.raises(ValueError):
            store.add_goal(title, target, currency=currency, due_month=due_month)


def test_allocations_accumulate_and_progress(store):
    gid = store.add_goal("Подушка", 100_000_00)
    assert store.add_allocation(gid, "2026-09-10", 30_000_00) > 0
    store.add_allocation(gid, "2026-09-20", 15_000_00)

    p = store.goal_progress(gid)
    assert p["allocated_kopecks"] == 45_000_00
    assert p["remaining_kopecks"] == 55_000_00
    assert p["done"] is False
    assert p["allocations"] == 2

    # Изъятие (подписанные копейки) уменьшает накопленное: деньги из конверта «вынимаются».
    store.add_allocation(gid, "2026-09-25", -5_000_00)
    assert store.goal_progress(gid)["allocated_kopecks"] == 40_000_00

    # Перевыполнение: done, остаток неотрицателен.
    store.add_allocation(gid, "2026-09-28", 90_000_00)
    p = store.goal_progress(gid)
    assert p["done"] is True and p["remaining_kopecks"] == 0

    allocs = store.list_allocations(gid)
    assert [a["amount_kopecks"] for a in allocs] == [30_000_00, 15_000_00, -5_000_00, 90_000_00]


def test_allocation_validations(store):
    gid = store.add_goal("Техника", 80_000_00)
    with pytest.raises(ValueError):
        store.add_allocation(999, "2026-09-10", 100_00)  # цели нет
    with pytest.raises(ValueError):
        store.add_allocation(gid, "2026-09-10", 0)  # нулевой взнос
    with pytest.raises(ValueError):
        store.add_allocation(gid, "20260910", 100_00)  # формат даты
    with pytest.raises(ValueError):
        store.add_allocation(gid, "2026-02-31", 100_00)  # несуществующий день
    with pytest.raises(ValueError):
        store.add_allocation(gid, "2099-01-01", 100_00)  # будущее
    with pytest.raises(ValueError):
        store.goal_progress(999)  # прогресс несуществующей цели
    store.archive_goal(gid)
    with pytest.raises(ValueError):
        store.add_allocation(gid, "2026-09-10", 100_00)  # архивная цель не пополняется


def test_archive_hides_from_default_list(store):
    g1 = store.add_goal("Первый", 100_00)
    g2 = store.add_goal("Второй", 100_00)
    assert store.archive_goal(g1) is True
    assert [g["id"] for g in store.list_goals()] == [g2]
    assert sorted(g["id"] for g in store.list_goals(include_archived=True)) == [g1, g2]
    assert store.archive_goal(999) is False  # несуществующую — тихий False

    store.add_allocation(g2, "2026-09-05", 50_00)
    store.archive_goal(g2)
    assert len(store.list_allocations(g2)) == 1  # история взносов не пропадает


def test_sql_layer_guards(store):
    """STRICT/CHECK — второй рубеж: мимо Python-валидации всё равно не пройдёт."""
    now = "2026-09-01T00:00:00+00:00"
    with pytest.raises(sqlite3.IntegrityError):  # цель 0 копеек
        store.conn.execute(
            "INSERT INTO goals(title, target_kopecks, currency, created_month, created, updated)"
            " VALUES('X', 0, 'RUB', '2026-09', ?, ?)", (now, now))
    store.conn.rollback()
    with pytest.raises(sqlite3.IntegrityError):  # валюта не ISO-3 (lowercase)
        store.conn.execute(
            "INSERT INTO goals(title, target_kopecks, currency, created_month, created, updated)"
            " VALUES('X', 100, 'rub', '2026-09', ?, ?)", (now, now))
    store.conn.rollback()

    gid = store.add_goal("Цель", 100_00)
    with pytest.raises(sqlite3.IntegrityError):  # взнос 0 копеек
        store.conn.execute(
            "INSERT INTO goal_allocations(goal_id, date, amount_kopecks, created_at)"
            " VALUES(?, '2026-09-01', 0, ?)", (gid, now))
    store.conn.rollback()
    with pytest.raises(sqlite3.IntegrityError):  # дата вне формата
        store.conn.execute(
            "INSERT INTO goal_allocations(goal_id, date, amount_kopecks, created_at)"
            " VALUES(?, '01.09.2026', 100, ?)", (gid, now))
    store.conn.rollback()
    store.add_allocation(gid, "2026-09-02", 100)
    with pytest.raises(sqlite3.IntegrityError):  # FK RESTRICT: удаление цели с взносами запрещено
        store.conn.execute("DELETE FROM goals WHERE id=?", (gid,))
    store.conn.rollback()


def test_add_transaction_rejects_invalid_dates(store):
    """Ревью wave5 S5: календарная валидация даты в Store (CHECK — только второй рубеж)."""
    for bad in ("2026-13-01", "2026-02-31", "20260901", ""):
        with pytest.raises(ValueError):
            store.add_transaction(date=bad, description="X", amount_kopecks=-100,
                                  category="groceries", category_source="rule")


def test_add_goal_rejects_over_limit(store):
    """Ревью wave5 S4: лимит суммы общий с API/импортом (form-путь не шире JSON)."""
    with pytest.raises(ValueError):
        store.add_goal("X", MAX_AMOUNT_KOPECKS + 1)


def test_goals_v7_on_fresh_and_legacy_db(tmp_path):
    fresh = Store(db_path=tmp_path / "fresh.db")
    assert fresh._user_version() == SCHEMA_VERSION >= 7
    assert fresh.conn.execute("SELECT COUNT(*) FROM goals").fetchone()[0] == 0
    assert fresh.conn.execute("SELECT COUNT(*) FROM goal_allocations").fetchone()[0] == 0

    legacy = tmp_path / "legacy6.db"
    con = sqlite3.connect(legacy)
    con.executescript(_TX_DDL)
    con.execute(
        "INSERT INTO transactions(date, description, amount_kopecks, category, category_source,"
        " created, updated) VALUES('2026-09-01','ЛЕНТА',-100,'Продукты','rule',"
        "'2026-09-01T00:00:00+00:00','2026-09-01T00:00:00+00:00')")
    con.execute("PRAGMA user_version = 6")
    con.commit()
    con.close()

    s = Store(db_path=legacy)  # апгрейд v6 → v7 аддитивен: данные и схема транзакций не тронуты
    assert s._user_version() == SCHEMA_VERSION
    assert s.conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 1
    assert s.conn.execute("SELECT COUNT(*) FROM goals").fetchone()[0] == 0
