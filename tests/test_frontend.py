from __future__ import annotations

from spendtrack.routers.frontend import _shift_month


def test_shift_month_boundaries():
    """Абсолютная навигация: переходы через границы года."""
    assert _shift_month("2026-09", -1) == "2026-08"
    assert _shift_month("2026-01", -1) == "2025-12"
    assert _shift_month("2026-12", 1) == "2027-01"
    assert _shift_month("2026-09", 4) == "2027-01"
