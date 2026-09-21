"""Контроль целостности файлов: sha256-хелпер для offsite-копий бэкапа.

Общий шов `scripts/backup.py` (считает и пишет хэш копии) и `doctor` (сверяет
внешнюю копию с маркером). Офлайн, без состояния.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path

_CHUNK = 1 << 20


def sha256_file(path: Path, chunk_size: int = _CHUNK) -> str:
    """sha256 файла потоком (не читает файл целиком в память)."""
    h = sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(chunk_size), b""):
            h.update(block)
    return h.hexdigest()
