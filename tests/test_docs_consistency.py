"""Contradiction-check публичных доков (M11): машино-проверяемые каноны. Оффлайн, без сети.

Ловит расхождения между публичными файлами до того, как их найдёт читатель:
цена/перки (README ↔ лендинг), порог авто-приёма (config ↔ лендинг), лицензия (LICENSE ↔ README ↔ лендинг),
банки (BANKS ↔ README ↔ лендинг), выключенный FUNDING до запуска. Семантические противоречия —
отдельным прогоном (см. `spec/PIPELINE.md` §Contradiction-check).
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
LANDING = ROOT / "landing" / "index.html"
FUNDING = ROOT / ".github" / "FUNDING.yml"


def _flat(path: Path) -> str:
    """Текст без переводов строк: подстроки не зависят от переносов в markdown."""
    return " ".join(path.read_text(encoding="utf-8").split())


def test_price_canon():
    for document in (README, LANDING):
        text = _flat(document)
        assert "1900" in text, f"{document.name}: нет цены 1900 ₽"
        assert "$25" in text or "25 $" in text, f"{document.name}: нет цены $25"


def test_confidence_threshold_matches_config():
    with (ROOT / "config" / "settings.toml").open("rb") as fh:
        threshold = tomllib.load(fh)["acceptance"]["auto_accept_confidence"]
    match = re.search(r"(?:≥|>=)\s*([\d.]+)", _flat(LANDING))
    assert match, "лендинг не упоминает порог авто-приёма"
    assert float(match.group(1)) == float(threshold), (
        f"лендинг: порог {match.group(1)} ≠ {threshold} из settings.toml"
    )


def test_license_canon():
    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "AGPLv3" in _flat(README)
    assert "AGPLv3" in _flat(LANDING)


def test_banks_canon():
    from spendtrack.csv_import import BANKS

    names = {"sber": "Сбер", "tinkoff": "Т-Банк", "yandex": "ЮMoney"}
    actual = set(BANKS) - {"auto"}
    extra, missing = actual - set(names), set(names) - actual
    assert not extra and not missing, f"BANKS vs канон названий: лишние {extra}, без названия {missing}"
    for document in (README, LANDING):
        text = _flat(document)
        for bank in names.values():
            assert bank in text, f"{document.name}: нет банка {bank}"


def test_supporter_perks_canon():
    perk = "имя в README и CHANGELOG"
    assert perk in _flat(README), "README: нет канона перка"
    assert perk in _flat(LANDING), "лендинг: нет канона перка"


def test_funding_disabled_until_launch():
    text = FUNDING.read_text(encoding="utf-8")
    active = [line for line in text.splitlines() if "boosty.to" in line and not line.lstrip().startswith("#")]
    assert not active, "FUNDING.yml содержит активную ссылку Boosty до запуска"


def _normalize_urls(text: str) -> list[str]:
    return re.findall(r"https?://[^\s\"'<>]+", text)


def test_install_urls_match_between_docs():
    """README и лендинг называют одни и те же URL установки (расхождение = читатель наткнётся на 404)."""
    readme_install = {u for u in _normalize_urls(_flat(README)) if "install" in u}
    landing_install = {u for u in _normalize_urls(_flat(LANDING)) if "install" in u}
    assert readme_install, "README: нет URL установки"
    assert landing_install, "лендинг: нет URL установки"
    assert readme_install == landing_install, f"URL установки разошлись: {readme_install ^ landing_install}"
