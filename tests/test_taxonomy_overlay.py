"""BY-overlay таксономии (Ф1): opt-in пакет правил `taxonomy.by.toml` — не дефолт.

Адъюдикация 03.10: overlay-механизм принят (opt-in файл, подключаемый настройкой
`taxonomy_overlay`); отдельный «disabled»-флаг правил — отклонён. Проверяем: без настройки
BY-мерчанты не матчатся; с настройкой — матчатся в свои категории; базовые правила не
подменяются; отсутствующий файл и небезопасное имя набора — тихо игнорируются (без падений).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from spendtrack.categorize import categorize_rules_only
from spendtrack.store import Store
from spendtrack.taxonomy import load_taxonomy

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def store(tmp_path):
    s = Store(db_path=tmp_path / "tax.db")
    yield s
    s.close()


def _cfg(tmp_path: Path, settings: str = "") -> Path:
    """Минимальный конфиг: базовая таксономия репо + settings.toml как в файле."""
    (tmp_path / "taxonomy.toml").write_bytes((ROOT / "config" / "taxonomy.toml").read_bytes())
    (tmp_path / "settings.toml").write_text(settings, encoding="utf-8")
    return tmp_path


def _cat(desc: str, taxonomy, store) -> str | None:
    return categorize_rules_only({"description": desc, "merchant": desc}, taxonomy, store)


def test_overlay_off_by_default(tmp_path, store, monkeypatch):
    """Без настройки пакет не подключён: BY-мерчанты остаются нерешёнными (opt-in, не дефолт)."""
    monkeypatch.delenv("SPENDTRACK_TAXONOMY_OVERLAY", raising=False)
    tax = load_taxonomy(_cfg(tmp_path))
    assert _cat("ЕВРООПТ №12 МИНСК", tax, store) is None
    assert _cat("БЕЛОРУСНЕФТЬ АЗС 3", tax, store) is None


def test_overlay_enabled_via_settings_toml(tmp_path, store, monkeypatch):
    monkeypatch.delenv("SPENDTRACK_TAXONOMY_OVERLAY", raising=False)
    tax = load_taxonomy(_cfg(tmp_path, 'taxonomy_overlay = "by"\n'))
    assert _cat("ЕВРООПТ №12 МИНСК", tax, store) == "groceries"
    assert _cat("БЕЛОРУСНЕФТЬ АЗС 3", tax, store) == "fuel"
    assert _cat("ЕРИП ПЛАТЕЖ", tax, store) == "utilities"
    assert _cat("ОПЛАТА A1 УСЛУГИ", tax, store) == "internet-phone"
    assert _cat("МИНСКТРАНС ТАЛОН", tax, store) == "transport"
    assert _cat("21VEK.BY ЗАКАЗ", tax, store) == "household"
    assert _cat("ЗАЧИСЛЕНИЕ ПО ВЕДОМОСТИ", tax, store) == "income"
    assert _cat("ЗАЧИСЛЕНИЕ ЗАРПЛАТЫ", tax, store) == "income"  # стем: родительный падеж в выписках
    assert _cat("УПЛАТА ПРОЦЕНТОВ", tax, store) is None  # overlay не «ловит всё подряд»


def test_overlay_enabled_via_env(tmp_path, store, monkeypatch):
    monkeypatch.setenv("SPENDTRACK_TAXONOMY_OVERLAY", "by")
    tax = load_taxonomy(_cfg(tmp_path))
    assert _cat("САНТА РИТЕЙЛ 44", tax, store) == "groceries"


def test_overlay_keeps_base_rules(tmp_path, store, monkeypatch):
    """Правила overlay добавляются ПОСЛЕ базовых: RU-правила сохраняют приоритет."""
    monkeypatch.setenv("SPENDTRACK_TAXONOMY_OVERLAY", "by")
    tax = load_taxonomy(_cfg(tmp_path))
    assert _cat("ООО ЛЕНТА 1234", tax, store) == "groceries"
    assert _cat("МЕТРО ТУРНИКЕТ", tax, store) == "transport"
    assert _cat("NETFLIX.COM", tax, store) == "subscriptions"


def test_overlay_missing_file_ignored(tmp_path, store, monkeypatch):
    monkeypatch.setenv("SPENDTRACK_TAXONOMY_OVERLAY", "no-such-pack")
    tax = load_taxonomy(_cfg(tmp_path))
    assert _cat("ЕВРООПТ №12", tax, store) is None  # набора нет — просто без overlay, без падений


def test_overlay_unsafe_name_ignored(tmp_path, store, monkeypatch):
    monkeypatch.setenv("SPENDTRACK_TAXONOMY_OVERLAY", "../../evil")
    tax = load_taxonomy(_cfg(tmp_path))
    assert _cat("ЕВРООПТ №12", tax, store) is None  # путь с «../» не строится


def test_overlay_config_file_overrides_packaged(tmp_path, store, monkeypatch):
    """Файл из каталога конфигурации перекрывает пакетный набор (один файл, не слияние)."""
    monkeypatch.setenv("SPENDTRACK_TAXONOMY_OVERLAY", "by")
    cfg = _cfg(tmp_path)
    (cfg / "taxonomy.by.toml").write_text(
        '[[rules]]\npattern = "ТЕСТ-МЕРЧАНТ"\ncategory = "fuel"\n', encoding="utf-8")
    tax = load_taxonomy(cfg)
    assert _cat("ТЕСТ-МЕРЧАНТ 1", tax, store) == "fuel"
    assert _cat("ЕВРООПТ №12", tax, store) is None


def test_overlay_can_add_categories(tmp_path, store, monkeypatch):
    """Категории overlay добавляются аддитивно по имени (движок merge — не только правила)."""
    monkeypatch.setenv("SPENDTRACK_TAXONOMY_OVERLAY", "custom")
    cfg = _cfg(tmp_path)
    (cfg / "taxonomy.custom.toml").write_text(
        '[[categories]]\nname = "by-specific"\ndisplay_name = "BY-специфика"\ncolor = "#111111"\n\n'
        '[[rules]]\npattern = "МЕРЧАНТ-Х"\ncategory = "by-specific"\n', encoding="utf-8")
    tax = load_taxonomy(cfg)
    assert tax.is_valid("by-specific")
    assert _cat("МЕРЧАНТ-Х 1", tax, store) == "by-specific"
