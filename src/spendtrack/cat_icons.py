"""Иконки категорий: разрешение «слаг → иконка» и рендер `<svg>` для Jinja (глобал `cat_icon`).

Цепочка выбора иконки: явное поле `icon` в `taxonomy.toml` → имя категории (у встроенных категорий
символ спрайта совпадает со слагом) → фолбэк `tag`. Кастомные категории выбирают иконку в настройках
(банк дополнительных символов в спрайте).

Спрайт — внешний `static/cat-icons.svg`: `<use href="…#i-<имя>">`, same-origin, `currentColor`
(практики MDN `<use>`). Кэш — по (путь, mtime): правки taxonomy.toml/спрайта видны без рестарта.
"""
from __future__ import annotations

import os
import tomllib
from functools import lru_cache
from pathlib import Path
from xml.etree import ElementTree

from markupsafe import Markup

from spendtrack.assets import static_url
from spendtrack.config import DEFAULTS_DIR, PKG_DIR, resolve_config_dir

FALLBACK_ICON = "tag"  # UPPER-константа: публичный контракт поведения (см. contract_delta snapshot)


def _taxonomy_file() -> Path:
    """Как taxonomy_repo: SPENDTRACK_TAXONOMY (тесты) → config-каталог → пакетный дефолт."""
    override = os.environ.get("SPENDTRACK_TAXONOMY")
    if override:
        return Path(override)
    base = Path(resolve_config_dir())
    path = base / "taxonomy.toml"
    return path if path.is_file() else DEFAULTS_DIR / "taxonomy.toml"


def _sprite_path() -> Path:
    return PKG_DIR / "static" / "cat-icons.svg"


@lru_cache(maxsize=4)
def _state(tax_path: str, tax_mtime: float, sprite_path: str, sprite_mtime: float) -> tuple[frozenset[str], dict[str, str]]:
    """(имена иконок спрайта, карта слаг→иконка) — пересчёт только при изменении файлов."""
    ids = frozenset(
        el.get("id", "")[2:] for el in ElementTree.parse(sprite_path).iter()
        if (el.get("id") or "").startswith("i-"))
    with open(tax_path, "rb") as f:
        data = tomllib.load(f)
    mapping: dict[str, str] = {}
    for c in data.get("categories", []):
        name = str(c.get("name", ""))
        cand = str(c.get("icon") or "").strip() or name
        mapping[name] = cand if cand in ids else FALLBACK_ICON
    return ids, mapping


def _current() -> tuple[frozenset[str], dict[str, str]]:
    tax, sprite = _taxonomy_file(), _sprite_path()
    return _state(str(tax), tax.stat().st_mtime, str(sprite), sprite.stat().st_mtime)


def icon_name(slug: str) -> str:
    """Имя иконки для слага категории (неизвестный слаг → фолбэк `tag`)."""
    return _current()[1].get(slug, FALLBACK_ICON)


def sprite_icon_names() -> list[str]:
    """Все имена иконок спрайта — для селектора в настройках."""
    return sorted(_current()[0])


def cat_icon(slug: str, cls: str = "cat-icon w-3.5 h-3.5 shrink-0") -> Markup:
    """Декоративная иконка категории (`aria-hidden`): смысл всегда остаётся в текстовом имени."""
    name = icon_name(slug)
    return Markup(
        f'<svg class="{cls}" aria-hidden="true" focusable="false">'
        f'<use href="{static_url("cat-icons.svg")}#i-{name}"></use></svg>')
