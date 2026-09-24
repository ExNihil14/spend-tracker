"""Dev-обёртка: логика — в `spendtrack/backup.py` (пользовательский CLI: `spendtrack backup`).

Использование:
    uv run python scripts/backup.py [--keep N] [--copy-to ПАПКА] [--force]
"""
from __future__ import annotations

from spendtrack.backup import main

if __name__ == "__main__":
    raise SystemExit(main())
