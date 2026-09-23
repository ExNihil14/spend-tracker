from __future__ import annotations

import tomllib
from pathlib import Path

from spendtrack.config import DEFAULTS_DIR, resolve_config_dir


class Category:
    def __init__(self, name: str, color: str, display_name: str | None = None):
        self.name = name
        self.color = color
        self.display_name = display_name or name


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
        return name in self._names

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
    categories = [Category(c["name"], c["color"], c.get("display_name")) for c in data["categories"]]
    rules = [Rule(r["pattern"], r["category"]) for r in data["rules"]]
    return Taxonomy(categories, rules)