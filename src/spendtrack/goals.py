"""Цели/копилки — read-only представление прогресса для UI/CLI (Ф1; движок советов — Ф2).

«Виртуальный конверт»: взносы — учёт намерения, деньги на счетах не блокируются; прогресс
считается на лету из `goal_allocations` (derived не храним, см. spec/ARCHITECTURE.md).
"""
from __future__ import annotations

from datetime import date

from spendtrack.store import Store


def goals_overview(store: Store, include_archived: bool = False) -> list[dict]:
    """Список целей с прогрессом: pct (0..100), allocated/remaining, взносы (журнал)."""
    out: list[dict] = []
    for goal in store.list_goals(include_archived=include_archived):
        gid = int(goal["id"])
        prog = store.goal_progress(gid)
        target, allocated = int(prog["target_kopecks"]), int(prog["allocated_kopecks"])
        if prog["done"]:
            pct = 100
        else:
            pct = max(0, min(99, allocated * 100 // target)) if target else 0
        out.append({
            "id": gid,
            "title": goal["title"],
            "currency": goal["currency"],
            "target_kopecks": target,
            "allocated_kopecks": allocated,
            "remaining_kopecks": int(prog["remaining_kopecks"]),
            "allocations_count": int(prog["allocations"]),
            "done": bool(prog["done"]),
            "pct": pct,
            "due_month": goal["due_month"],
            "created_month": goal["created_month"],
            "archived": int(goal["archived"]),
            "allocations": store.list_allocations(gid),
        })
    return out


def goals_snapshot(store: Store) -> dict:
    """Контекст страницы/фрагмента: активные + архивные + сегодня (дефолт даты взноса)."""
    all_goals = goals_overview(store, include_archived=True)
    return {
        "goals": [g for g in all_goals if not g["archived"]],
        "archived": [g for g in all_goals if g["archived"]],
        "today": date.today().isoformat(),  # noqa: DTZ011 — локальная календарная дата (дефолт формы)
    }
