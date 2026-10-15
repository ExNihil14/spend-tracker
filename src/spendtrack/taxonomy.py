from __future__ import annotations

import re
import tomllib
from pathlib import Path

from spendtrack.config import DEFAULTS_DIR, load_settings, resolve_config_dir


class Category:
    def __init__(self, name: str, color: str, display_name: str | None = None,
                 icon: str | None = None, discretionary: bool | None = None):
        self.name = name
        self.color = color
        self.display_name = display_name or name
        # Иконка: явное поле taxonomy.toml (имя символа спрайта); пусто — фолбэк-цепочка в cat_icons
        self.icon = (icon or "").strip()
        # Ф2 целей: флаг «дискреционная» — только такие категории попадают в советы what-if.
        # wave5 S1: None (флага нет в TOML) ОТЛИЧАЕТСЯ от явного False — иначе all-false конфиг
        # включал fallback и снова разрешал советы по запрещённым категориям.
        self.discretionary = None if discretionary is None else bool(discretionary)


class Rule:
    def __init__(self, pattern: str, category: str):
        self.pattern = pattern.upper()
        self.category = category


class Taxonomy:
    def __init__(self, categories: list[Category], rules: list[Rule]):
        self.categories = categories
        self.rules = rules
        self._names = {c.name for c in categories}
        self._display = {c.name: c.display_name for c in categories}

    def is_valid(self, name: str) -> bool:
        # C1 (Astra 01.10): нестроковое значение из ответа LLM/кэша не должно ронять проверку
        return isinstance(name, str) and name in self._names

    def display(self, name: str) -> str:
        """Отображаемое имя категории (RU); неизвестный слаг — как есть."""
        return self._display.get(name, name)


def load_taxonomy(config_dir: Path | None = None) -> Taxonomy:
    base = Path(config_dir) if config_dir else resolve_config_dir()
    path = base / "taxonomy.toml"
    if not path.is_file():
        path = DEFAULTS_DIR / "taxonomy.toml"  # установленный режим: дефолт из пакета
    with open(path, "rb") as f:
        data = tomllib.load(f)
    categories = [Category(c["name"], c.get("color", "#9ca3af"), c.get("display_name"),
                           c.get("icon"), c.get("discretionary", None))
                  for c in data.get("categories", [])]
    rules = [Rule(r["pattern"], r["category"]) for r in data.get("rules", [])]
    _apply_overlay(base, categories, rules)
    return Taxonomy(categories, rules)


def _apply_overlay(base: Path, categories: list[Category], rules: list[Rule]) -> None:
    """Opt-in пакет правил по локации (Ф1, адъюдикация 03.10): настройка `taxonomy_overlay`
    подключает файл `taxonomy.<имя>.toml` (каталог конфига → пакетный дефолт).

    Правила добавляются ПОСЛЕ базовых (базовые сохраняют приоритет); категории — аддитивно
    по имени. Пустое/небезопасное имя и отсутствие файла — тихо без overlay; битый TOML
    overlay — явная ошибка (как у taxonomy.toml). Битые настройки не роняют таксономию.
    """
    try:
        name = load_settings(base).taxonomy_overlay.strip()
    except (OSError, ValueError):
        return  # настройки не читаются — работаем без overlay (их покажет doctor)
    if not name or not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", name):
        return  # пустое/небезопасное имя: путь не строится (защита от «../»)
    for candidate in (base / f"taxonomy.{name}.toml", DEFAULTS_DIR / f"taxonomy.{name}.toml"):
        if candidate.is_file():
            overlay_path = candidate
            break
    else:
        return  # набора нет — просто без overlay
    try:
        with open(overlay_path, "rb") as f:
            odata = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"taxonomy.{name}.toml: {e}") from e
    known = {c.name for c in categories}
    categories.extend(
        c for c in (Category(oc["name"], oc.get("color", "#9ca3af"), oc.get("display_name"),
                             oc.get("icon"), oc.get("discretionary", None))
                    for oc in odata.get("categories", []))
        if c.name not in known)
    rules.extend(Rule(r["pattern"], r["category"]) for r in odata.get("rules", []))