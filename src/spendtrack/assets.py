"""Версионирование статики: `/static/<файл>?v=<hash>` (MDN cache-busting + immutable).

Хэш — sha256 содержимого (12 hex), кэшируется `lru_cache` по (путь, mtime): в dev правка файла даёт новый
URL без рестарта, а потокобезопасность обеспечивает сам `lru_cache` (без общего мутируемого словаря).
Шаблоны используют `{{ static('app.css') }}` (globals в роутерах), ответы `/static/*?v=` получают
`Cache-Control: public, max-age=31536000, immutable` (middleware в `main.py`).
"""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from spendtrack.config import PKG_DIR

_STATIC = PKG_DIR / "static"


@lru_cache(maxsize=64)
def _digest(path: str, mtime: float) -> str:
    """sha256 содержимого файла (12 hex); mtime в ключе — инвалидация при правке файла."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


def _version(path: Path) -> str:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return "0"
    return _digest(str(path), mtime)


def static_url(name: str) -> str:
    """URL статического файла с версией содержимого (безопасно для длинного immutable-кэша)."""
    return f"/static/{name}?v={_version(_STATIC / name)}"
