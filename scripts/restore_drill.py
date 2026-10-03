"""Совместимость: дрилл переехал в пакет `spendtrack.restore_drill` (тикет C2, 03.10.2026).

Тонкий шим: `python -m scripts.restore_drill` и старые импорты продолжают работать;
источник истины — `spendtrack/restore_drill.py`.
"""
from __future__ import annotations

from spendtrack.restore_drill import (
    inspect_db,
    latest_backup,
    live_stats,
    main,
    run_restore_drill,
)

__all__ = ["inspect_db", "latest_backup", "live_stats", "main", "run_restore_drill"]

if __name__ == "__main__":
    raise SystemExit(main())
