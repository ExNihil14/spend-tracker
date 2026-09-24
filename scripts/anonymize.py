"""Dev-обёртка: логика — в `spendtrack/anonymize.py` (пользовательский CLI: `spendtrack anonymize`).

Использование:
    uv run python scripts/anonymize.py выписка.csv [образец.csv] [--rows 0] [--anon-column "ФИО"]

Для фикстур (полный файл) явно укажите `--rows 0`.
"""
from __future__ import annotations

from spendtrack.anonymize import main

if __name__ == "__main__":
    raise SystemExit(main())
