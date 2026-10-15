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


def _flat_html(path: Path) -> str:
    """HTML без комментариев и тегов: канон ищется в ВИДИМОМ тексте.

    wave12 S6: первый «≥» в документе мог стоять в комментарии или другой разметке, а не в каноне.
    """
    html = re.sub(r"<!--.*?-->", " ", path.read_text(encoding="utf-8"), flags=re.S)
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def test_price_canon():
    """Цены — полные числа с валютой (wave12 S6: подстроки «1900» ⊂ «19000», «$25» ⊂ «$250»;
    в лендинге цена берётся из конкретного элемента .price, а не из всего документа)."""
    readme = _flat(README)
    assert re.search(r"1900\s*₽", readme), "README: нет полной цены 1900 ₽"
    assert re.search(r"\$25(?!\d)", readme), "README: нет полной цены $25"
    price = re.search(r'<div class="price">(.*?)</div>',
                      LANDING.read_text(encoding="utf-8"), re.S)
    assert price, "лендинг: нет элемента .price с ценой"
    assert re.search(r"1900\s*₽", price.group(1)), (
        f"лендинг .price: нет полной цены 1900 ₽: {price.group(1)!r}"
    )
    assert re.search(r"\$25(?!\d)", price.group(1)), (
        f"лендинг .price: нет полной цены $25: {price.group(1)!r}"
    )


def test_confidence_threshold_matches_config():
    """Порог — из предложения «Порог уверенности: ≥ …» в видимом тексте (wave12 S6: первый «≥»
    в документе мог стоять в комментарии/иной разметке, а не в каноне)."""
    with (ROOT / "config" / "settings.toml").open("rb") as fh:
        threshold = tomllib.load(fh)["acceptance"]["auto_accept_confidence"]
    match = re.search(r"Порог уверенности:\s*(?:≥|>=)\s*([\d.]+)", _flat_html(LANDING))
    assert match, "лендинг: нет предложения «Порог уверенности: ≥ …»"
    assert float(match.group(1)) == float(threshold), (
        f"лендинг: порог {match.group(1)} ≠ {threshold} из settings.toml"
    )


def test_license_canon():
    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "AGPLv3" in _flat(README)
    assert "AGPLv3" in _flat(LANDING)


def test_banks_canon():
    from spendtrack.csv_import import BANKS

    names = {"sber": "Сбер", "tinkoff": "Т-Банк", "yandex": "ЮMoney", "priorbank": "Приорбанк"}
    actual = set(BANKS) - {"auto"}
    extra, missing = actual - set(names), set(names) - actual
    assert not extra and not missing, f"BANKS vs канон названий: лишние {extra}, без названия {missing}"
    for document in (README, LANDING):
        text = _flat(document)
        for bank in names.values():
            assert bank in text, f"{document.name}: нет банка {bank}"


def test_privacy_prompt_injection_wording():
    """wave12 (адъюдикация policy, S4): PRIVACY не переобещает «prompt-injection защищён» —
    валидация ограничивает, но не исключает вред (существующая-неверная категория может пройти)."""
    text = _flat(ROOT / "PRIVACY.md")
    assert "не исключает" in text
    assert "Prompt-injection защищён" not in text


def test_supporter_perks_canon():
    perk = "имя в README и CHANGELOG"
    assert perk in _flat(README), "README: нет канона перка"
    assert perk in _flat(LANDING), "лендинг: нет канона перка"


# GitHub-поля кнопки Sponsor (поддерживаемые имена: значение обязано быть пустым до запуска).
FUNDING_FIELDS = {
    "github", "patreon", "open_collective", "ko_fi", "tidelift", "community_bridge",
    "liberapay", "issuehunt", "lfx_crowdfunding", "polar", "buy_me_a_coffee",
    "thanks_dev", "custom",
}


def test_funding_disabled_until_launch():
    """wave12 (S7): контракт «FUNDING выключен до запуска» — все АКТИВНЫЕ поля пусты.

    Прежняя проверка видела только буквальный `boosty.to`; проходили активный `custom` на
    другом домене (G1) и YAML-escape `boosty\\u002eto`, который поиск не декодирует (G2)."""
    active = [line.strip() for line in FUNDING.read_text(encoding="utf-8").splitlines()
              if line.strip() and not line.strip().startswith("#")]
    for line in active:
        key, _, value = line.partition(":")
        assert key.strip() in FUNDING_FIELDS, f"FUNDING.yml: неизвестное funding-поле: {line!r}"
        assert value.strip() in ("", "[]"), (
            f"FUNDING.yml: активная ссылка при выключенном FUNDING: {line!r}"
        )


def _normalize_urls(text: str) -> list[str]:
    return re.findall(r"https?://[^\s\"'<>]+", text)


def test_install_urls_match_between_docs():
    """README и лендинг называют одни и те же URL установки (расхождение = читатель наткнётся на 404)."""
    readme_install = {u for u in _normalize_urls(_flat(README)) if "install" in u}
    landing_install = {u for u in _normalize_urls(_flat(LANDING)) if "install" in u}
    assert readme_install, "README: нет URL установки"
    assert landing_install, "лендинг: нет URL установки"
    assert readme_install == landing_install, f"URL установки разошлись: {readme_install ^ landing_install}"


def test_fingerprint_canon_matches_code():
    """C1 wave11/agentdocs + wave12 (S8): канон fingerprint во всех доках совпадает с кодом.

    Код (`store.py::fingerprint`): валютный суффикс `|CUR` — КОД валюты для ≠ RUB (base-независимо,
    wave5 C1). Точные отпечатки закреплены для RUB/BYN/USD; формула в доках сравнивается ЦЕЛИКОМ
    (wave12 S8: проверка начала/конца пропускала подмену середины формулы).
    """
    import hashlib

    from spendtrack.store import fingerprint

    rub = fingerprint("2026-01-01", -12345, "abc", "acc", "1")
    assert rub == hashlib.sha1(b"2026-01-01|-12345|ABC|acc|1").hexdigest(), (
        "код: RUB-отпечаток обязан быть без валютного суффикса"
    )
    byn = fingerprint("2026-01-01", -12345, "abc", "acc", "1", currency="BYN")
    usd = fingerprint("2026-01-01", -12345, "abc", "acc", "1", currency="USD")
    assert byn == hashlib.sha1(b"2026-01-01|-12345|ABC|acc|1|BYN").hexdigest(), (
        "код: не-RUB-суффикс обязан быть КОДОМ валюты (не константой для всех не-RUB)"
    )
    assert usd == hashlib.sha1(b"2026-01-01|-12345|ABC|acc|1|USD").hexdigest(), (
        "код: не-RUB-суффикс обязан быть КОДОМ валюты (не константой для всех не-RUB)"
    )
    assert byn != usd, "код: разные не-RUB валюты обязаны давать разные отпечатки (дедуп не склеивает)"

    formulas = {
        "sha1(date|amount|desc|account_anon|export_rowid)",
        "sha1(date|kopecks|norm(desc)|account_anon|export_rowid)",  # CONTEXT.md: словарь терминов
    }
    docs = (ROOT / "AGENTS.md", ROOT / "spec" / "stack.md", ROOT / "CONTEXT.md",
            ROOT / ".opencode" / "skills" / "bank-adapter" / "SKILL.md")
    for doc in docs:
        text = _flat(doc)
        match = re.search(r"sha1\(date\|[^\s]*\)", text)
        assert match, f"{doc}: нет канонической формулы fingerprint"
        assert match.group(0) in formulas, (
            f"{doc}: формула изменилась: {match.group(0)!r} (канон: {sorted(formulas)})"
        )
        window = text[max(0, match.start() - 160): match.start() + 260]
        assert "|CUR" in window, f"{doc}: формула без валютного суффикса `|CUR` рядом с местом канона"
        assert "≠ RUB" in window or "не-RUB" in window, (
            f"{doc}: не сказано, что суффикс — для валюты ≠ RUB"
        )
        assert "только для НЕ-базовой" not in text, (
            f"{doc}: устаревшая формулировка «только для НЕ-базовой» (правильно: ≠ RUB, base-независимо)"
        )
