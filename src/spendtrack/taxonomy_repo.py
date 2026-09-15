"""Безопасная работа с config/taxonomy.toml из UI (атомарная запись, бэкап, аудит).

Дизайн: EXPERT_TAXONOMY_UI_DESIGN.md. Валидация строгая; после записи — parse-back проверка;
перед записью — сверка sha256 (защита от параллельной ручной правки); сериализация — только
whitelisted-поля (name/color/pattern/category), значения экранируются валидацией.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import tomllib
from datetime import UTC, datetime
from pathlib import Path

from spendtrack.config import CONFIG_DIR
from spendtrack.store import Store

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
    _audit(action, key, old, new)


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


def usage_counts(store: Store) -> dict[str, int]:
    rows = store.conn.execute(
        "SELECT category, COUNT(1) n FROM transactions GROUP BY category").fetchall()
    return {r["category"]: r["n"] for r in rows}


# ---- тестер каскада (read-only) ----

def test_description(description: str, store: Store) -> dict:
    desc = (description or "").strip().upper()
    data = load_raw()
    matched = [
        {"index": i, "pattern": r["pattern"], "category": r["category"]}
        for i, r in enumerate(data.get("rules", []))
        if r["pattern"] in desc
    ]
    cached = store.merchant_cache_get(desc)
    winner = cached or (matched[0]["category"] if matched else None)
    return {"description": desc, "matched": matched, "cached": cached, "winner": winner,
            "source": "merchant_cache" if cached else ("rule" if matched else "llm/offline")}
