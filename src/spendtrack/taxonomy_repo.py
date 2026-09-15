"""Безопасная работа с config/taxonomy.toml из UI (атомарная запись, бэкап, аудит).

Дизайн: EXPERT_TAXONOMY_UI_DESIGN.md. Валидация строгая; после записи — parse-back проверка;
перед записью — сверка sha256 (защита от параллельной ручной правки); сериализация — только
whitelisted-поля (name/color/pattern/category), значения экранируются валидацией.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import tempfile
import tomllib
from datetime import UTC, datetime
from decimal import InvalidOperation
from pathlib import Path

from spendtrack.config import CONFIG_DIR
from spendtrack.reports import BUDGET_EXCLUDED
from spendtrack.store import Store, parse_amount

logger = logging.getLogger(__name__)

COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,31}$")
PATTERN_FORBIDDEN = ('"', "\\", "\n", "\r", "\t")

MAX_RULES = 500


def _taxonomy_path() -> Path:
    """Путь к taxonomy.toml (env SPENDTRACK_TAXONOMY — для тестов; по умолчанию config/)."""
    override = os.environ.get("SPENDTRACK_TAXONOMY")
    return Path(override) if override else CONFIG_DIR / "taxonomy.toml"


def _audit_path() -> Path:
    return _taxonomy_path().with_name("taxonomy_audit.jsonl")


class TaxonomyError(ValueError):
    """Ошибка валидации/конфликта (показывается пользователю)."""


def load_raw() -> dict:
    with open(_taxonomy_path(), "rb") as f:
        return tomllib.load(f)


def file_hash() -> str:
    return hashlib.sha256(_taxonomy_path().read_bytes()).hexdigest()


def validate_color(color: str) -> str:
    color = (color or "").strip()
    if not COLOR_RE.match(color):
        raise TaxonomyError("цвет должен быть в формате #RRGGBB")
    return color.lower()


def validate_name(name: str) -> str:
    name = (name or "").strip().lower()
    if not NAME_RE.match(name):
        raise TaxonomyError("имя: 2-32 символа, латиница/цифры/дефис, начинается с буквы или цифры")
    return name


def validate_pattern(pattern: str) -> str:
    pattern = (pattern or "").strip().upper()
    if not (2 <= len(pattern) <= 64) or any(bad in pattern for bad in PATTERN_FORBIDDEN):
        raise TaxonomyError("паттерн: 2-64 символа, без кавычек/слэшей/переносов")
    return pattern


def _audit(action: str, key: str, old, new) -> None:
    entry = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "pid": os.getpid(),
        "action": action,
        "key": key,
        "old": old,
        "new": new,
    }
    with open(_audit_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _dump(data: dict) -> str:
    lines: list[str] = []
    for c in data.get("categories", []):
        lines += ["[[categories]]", f'name = "{c["name"]}"', f'color = "{c["color"]}"', ""]
    for r in data.get("rules", []):
        lines += ["[[rules]]", f'pattern = "{r["pattern"]}"', f'category = "{r["category"]}"', ""]
    return "\n".join(lines)


def save(data: dict, expected_hash: str | None, action: str, key: str, old=None, new=None) -> None:
    if expected_hash and expected_hash != file_hash():
        raise TaxonomyError("файл taxonomy.toml изменён снаружи — обновите страницу и повторите")
    text = _dump(data)
    back = tomllib.loads(text)  # parse-back: структура обязана остаться валидной
    if len(back.get("categories", [])) != len(data.get("categories", [])) or \
       len(back.get("rules", [])) != len(data.get("rules", [])):
        raise TaxonomyError("внутренняя ошибка сериализации TOML")

    path = _taxonomy_path()
    if path.exists():  # бэкап предыдущей версии
        path.with_suffix(".toml.bak").write_bytes(path.read_bytes())

    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)  # атомарно
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    try:
        _audit(action, key, old, new)  # после replace: сбой аудита не должен ронять операцию
    except OSError:
        logger.warning("taxonomy audit write failed (action=%s key=%s)", action, key, exc_info=True)


# ---- операции ----

def _find_category(data: dict, name: str) -> dict:
    for c in data.get("categories", []):
        if c["name"].lower() == name.lower():
            return c
    raise TaxonomyError(f"категория {name} не найдена")


def add_category(name: str, color: str, expected_hash: str | None) -> None:
    name, color = validate_name(name), validate_color(color)
    data = load_raw()
    if any(c["name"].lower() == name for c in data.get("categories", [])):
        raise TaxonomyError(f"категория {name} уже существует")
    data.setdefault("categories", []).append({"name": name, "color": color})
    save(data, expected_hash, "add_category", name, None, {"name": name, "color": color})


def set_color(name: str, color: str, expected_hash: str | None) -> None:
    color = validate_color(color)
    data = load_raw()
    cat = _find_category(data, name)
    old = cat["color"]
    cat["color"] = color
    save(data, expected_hash, "set_color", cat["name"], old, color)


def delete_category(name: str, store: Store, expected_hash: str | None) -> None:
    data = load_raw()
    cat = _find_category(data, name)
    real = cat["name"]
    used = usage_counts(store).get(real, 0)
    if used:
        raise TaxonomyError(f"категория используется ({used}) — удаление запрещено")
    if any(r["category"] == real for r in data.get("rules", [])):
        raise TaxonomyError("категория используется в правилах — сначала удалите/переназначьте правила")
    data["categories"] = [c for c in data.get("categories", []) if c["name"] != real]
    save(data, expected_hash, "delete_category", real, {"name": real}, None)
    if store.budget_map().get(real):  # бюджет уходит вместе с категорией (после успешной записи TOML)
        try:
            store.clear_budget(real)
        except sqlite3.Error:
            logger.warning("budget cleanup failed for deleted category %s", real, exc_info=True)


def usage_counts(store: Store) -> dict[str, int]:
    rows = store.conn.execute(
        "SELECT category, COUNT(1) n FROM transactions GROUP BY category").fetchall()
    return {r["category"]: r["n"] for r in rows}


# ---- бюджеты по категориям (БД) ----

def set_budget(category: str, amount: str, store: Store) -> None:
    """Установить/снять месячный бюджет категории (сумма в рублях; пусто/0 — снять)."""
    data = load_raw()
    name = _canonical_category(data, category)
    if name in BUDGET_EXCLUDED:
        raise TaxonomyError(f"категория «{name}» не бюджетируется (доход/перевод)")
    raw = (amount or "").strip()
    if not raw:
        store.clear_budget(name)
        return
    try:
        value = parse_amount(raw)
    except (InvalidOperation, ValueError):
        raise TaxonomyError("сумма должна быть числом (например, 20000 или 20000.50)") from None
    if value == 0:
        store.clear_budget(name)
        return
    if value < 0:
        raise TaxonomyError("бюджет не может быть отрицательным")
    store.set_budget(name, value)


# ---- переименование категории (миграция TOML + БД) ----

def _rename_targets(data: dict, old_name: str, new_name: str) -> tuple[str, str]:
    cat = _find_category(data, old_name)
    old = cat["name"]
    new = validate_name(new_name)
    if new == old:
        raise TaxonomyError("новое имя совпадает с текущим — менять нечего")
    if any(c["name"].lower() == new for c in data.get("categories", [])):
        raise TaxonomyError(f"категория «{new}» уже существует")
    return old, new


def rename_counts(old: str, data: dict, store: Store) -> dict:
    def count(sql: str) -> int:
        return int(store.conn.execute(sql, (old,)).fetchone()[0])
    return {
        "transactions": count("SELECT COUNT(1) FROM transactions WHERE category=?"),
        "proposals": count("SELECT COUNT(1) FROM transactions WHERE category_llm=?"),
        "cache": count("SELECT COUNT(1) FROM merchant_cache WHERE category=?"),
        "examples": count("SELECT COUNT(1) FROM examples WHERE category=?"),
        "budget": count("SELECT COUNT(1) FROM budgets WHERE category=?"),
        "rules": sum(1 for r in data.get("rules", []) if r["category"] == old),
    }


def rename_preview(old_name: str, new_name: str, store: Store,
                   expected_hash: str | None = None) -> dict:
    """Предпросмотр переименования (read-only): имена + число затронутых записей."""
    data = load_raw()
    old, new = _rename_targets(data, old_name, new_name)
    if expected_hash and expected_hash != file_hash():
        raise TaxonomyError("файл taxonomy.toml изменён снаружи — обновите страницу и повторите")
    return {"old": old, "new": new, "counts": rename_counts(old, data, store),
            "file_hash": file_hash()}


def _migrate_db_category(store: Store, src: str, dst: str) -> None:
    with store.conn:  # одна транзакция: либо все таблицы, либо ни одной
        store.conn.execute("UPDATE transactions SET category=? WHERE category=?", (dst, src))
        store.conn.execute("UPDATE transactions SET category_llm=? WHERE category_llm=?", (dst, src))
        store.conn.execute("UPDATE merchant_cache SET category=? WHERE category=?", (dst, src))
        store.conn.execute("UPDATE examples SET category=? WHERE category=?", (dst, src))
        store.conn.execute("UPDATE budgets SET category=? WHERE category=?", (dst, src))


def rename_category(old_name: str, new_name: str, store: Store, expected_hash: str | None) -> dict:
    """Переименовать категорию: TOML (имя + правила) и БД (транзакции/предложения/кэш/примеры).

    save() атомарен и при сбое до replace не меняет файл, поэтому БД откатывается безопасно.
    """
    data = load_raw()
    old, new = _rename_targets(data, old_name, new_name)
    if expected_hash and expected_hash != file_hash():
        raise TaxonomyError("файл taxonomy.toml изменён снаружи — обновите страницу и повторите")
    counts = rename_counts(old, data, store)

    _migrate_db_category(store, old, new)
    try:
        _find_category(data, old)["name"] = new
        for r in data.get("rules", []):
            if r["category"] == old:
                r["category"] = new
        save(data, expected_hash, "rename_category", old, {"name": old}, {"name": new})
    except Exception:
        _migrate_db_category(store, new, old)  # откат БД; TOML не изменён
        raise
    return {"old": old, "new": new, "counts": counts}


# ---- операции с правилами ----

def _canonical_category(data: dict, category: str) -> str:
    name = (category or "").strip().lower()
    for c in data.get("categories", []):
        if c["name"].lower() == name:
            return c["name"]
    raise TaxonomyError(f"категория «{category}» не найдена")


def add_rule(pattern: str, category: str, expected_hash: str | None) -> None:
    pattern = validate_pattern(pattern)
    data = load_raw()
    canonical = _canonical_category(data, category)
    rules = data.get("rules", [])
    if len(rules) >= MAX_RULES:
        raise TaxonomyError(f"достигнут лимит правил ({MAX_RULES})")
    if any(r["pattern"].upper() == pattern for r in rules):
        raise TaxonomyError(f"правило «{pattern}» уже существует")
    rule = {"pattern": pattern, "category": canonical}
    rules.append(rule)
    data["rules"] = rules
    save(data, expected_hash, "add_rule", pattern, None, dict(rule))


def delete_rule(index: int, expected_hash: str | None) -> None:
    data = load_raw()
    rules = data.get("rules", [])
    if not 0 <= index < len(rules):
        raise TaxonomyError("правило не найдено (список изменился — обновите страницу)")
    removed = rules.pop(index)
    save(data, expected_hash, "delete_rule", removed["pattern"], dict(removed), None)


def move_rule(index: int, direction: str, expected_hash: str | None) -> None:
    data = load_raw()
    rules = data.get("rules", [])
    if not 0 <= index < len(rules):
        raise TaxonomyError("правило не найдено (список изменился — обновите страницу)")
    if direction not in ("up", "down"):
        raise TaxonomyError("направление перемещения: up|down")
    target = index - 1 if direction == "up" else index + 1
    if not 0 <= target < len(rules):
        raise TaxonomyError("правило уже в начале списка" if direction == "up"
                            else "правило уже в конце списка")
    rules[index], rules[target] = rules[target], rules[index]
    save(data, expected_hash, "move_rule", rules[target]["pattern"], index, target)


def analyze_rules(data: dict | None = None) -> list[dict]:
    """Диагностика порядка правил: дубли, «мёртвые» (перекрытые ранее) и битые категории.

    Правило мёртвое, если его не может выиграть ни одно описание: категории нет в
    таксономии, паттерн уже встречался раньше или любой матч перехватывает более
    раннее правило с подстрокой этого паттерна (first-match).
    """
    data = data if data is not None else load_raw()
    rules = data.get("rules", [])
    cats = {c["name"] for c in data.get("categories", [])}
    pats = [r["pattern"].upper() for r in rules]
    valid = [r["category"] in cats for r in rules]  # рантайм пропускает битые категории
    out: list[dict] = []
    for i, r in enumerate(rules):
        duplicate_of = None
        shadowed_by = None
        for j in range(i):
            if not valid[j]:  # битое правило в рантайме не срабатывает — не перехватчик
                continue
            if duplicate_of is None and pats[j] == pats[i]:
                duplicate_of = j
            if shadowed_by is None and pats[j] in pats[i]:
                shadowed_by = j
        out.append({
            "index": i,
            "pattern": r["pattern"],
            "category": r["category"],
            "invalid_category": not valid[i],
            "duplicate_of": duplicate_of,
            "duplicate_differs": duplicate_of is not None
            and rules[duplicate_of]["category"] != r["category"],
            "shadowed_by": shadowed_by,
            "shadows": [j for j in range(i + 1, len(rules))
                        if valid[i] and valid[j] and pats[i] in pats[j]],
            "dead": not valid[i] or duplicate_of is not None or shadowed_by is not None,
        })
    return out


def preview_rule(pattern: str, category: str) -> dict:
    """Предпросмотр правила, добавляемого в конец списка (без записи)."""
    pattern = validate_pattern(pattern)
    data = load_raw()
    _canonical_category(data, category)
    warnings: list[str] = []
    analysis = analyze_rules(data)
    for a in analysis:
        if a["pattern"].upper() == pattern:
            warnings.append(
                f"дубль: правило «{a['pattern']}» уже есть (#{a['index']}, {a['category']})")
            break
    for a in analysis:
        p = a["pattern"].upper()
        if a["invalid_category"]:
            continue  # битое правило не перехватывает — предупреждать не о чем
        if p != pattern and p in pattern:
            warnings.append(
                f"будет мёртвым: совпадение сначала ловит #{a['index']} «{a['pattern']}»"
                f" → {a['category']} (подтвердите и поднимите выше)")
            break
    return {"pattern": pattern, "warnings": warnings}


# ---- тестер каскада (read-only) ----

def test_description(description: str, store: Store) -> dict:
    desc = (description or "").strip().upper()
    data = load_raw()
    cats = {c["name"] for c in data.get("categories", [])}
    matched = [
        {"index": i, "pattern": r["pattern"], "category": r["category"],
         "valid": r["category"] in cats}
        for i, r in enumerate(data.get("rules", []))
        if r["pattern"] in desc
    ]
    cached = store.merchant_cache_get(desc)
    winner = cached or next((m["category"] for m in matched if m["valid"]), None)
    return {"description": desc, "matched": matched, "cached": cached, "winner": winner,
            "source": "merchant_cache" if cached else ("rule" if winner else "llm/offline")}
