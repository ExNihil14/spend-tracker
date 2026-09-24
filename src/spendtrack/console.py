"""Общий консольный шов: UTF-8 для stdout/stderr на RU-Windows.

Пайп/Git Bash на RU-Windows отдаёт cp1251: кириллица мазалась, а «≠» ронял печать.
Реальная консоль Windows уже UTF-8 (PEP 528) — там no-op; pytest-capture тоже UTF-8.
"""
from __future__ import annotations

import sys


def utf8_stdout() -> None:
    """Переключает текстовые потоки на UTF-8, если они не UTF-8 (stdout и stderr)."""
    for stream in (sys.stdout, sys.stderr):
        enc = (getattr(stream, "encoding", "") or "").lower()
        if enc not in ("utf-8", "utf8") and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
