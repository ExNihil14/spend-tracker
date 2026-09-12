from __future__ import annotations

import tomllib
from pathlib import Path

from spendtrack.config import CONFIG_DIR


class Category:
    def __init__(self, name: str, color: str):
        self.name = name
        self.color = color


class Rule:
    def __init__(self, pattern: str, category: str):
        self.pattern = pattern.upper()
        self.category = category


class Taxonomy:
    def __init__(self, categories: list[Category], rules: list[Rule]):
        self.categories = categories
        self.rules = rules
        self._names = {c.name for c in categories}

    def is_valid(self, name: str) -> bool:
        return name in self._names


def load_taxonomy(config_dir: Path | None = None) -> Taxonomy:
    config_dir = config_dir or CONFIG_DIR
    with open(config_dir / "taxonomy.toml", "rb") as f:
        data = tomllib.load(f)
    categories = [Category(c["name"], c["color"]) for c in data["categories"]]
    rules = [Rule(r["pattern"], r["category"]) for r in data["rules"]]
    return Taxonomy(categories, rules)