"""Иконки категорий: внешний SVG-спрайт + Jinja-макрос (usage-first: публичные страницы).

Практики (MDN <use>, проверено 30.09.2026): внешний `href` — same-origin; презентационные
атрибуты — на <symbol> (currentColor наследуется от места использования); иконка декоративна
(`aria-hidden`), имя категории всегда остаётся текстом. Спрайт офлайн: без JS и внешних ссылок.
"""
from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

from fastapi.testclient import TestClient

from spendtrack.main import app
from spendtrack.store import Store
from spendtrack.taxonomy import load_taxonomy

ROOT = Path(__file__).resolve().parents[1]
SPRITE = ROOT / "src" / "spendtrack" / "static" / "cat-icons.svg"
SVG_NS = "{http://www.w3.org/2000/svg}"


def test_sprite_covers_taxonomy_and_is_valid():
    tree = ET.parse(SPRITE)
    symbols = {el.get("id"): el for el in tree.iter(f"{SVG_NS}symbol")}
    slugs = {c.name for c in load_taxonomy().categories}
    missing = {f"i-{s}" for s in slugs} - set(symbols)
    assert not missing, f"нет иконок для категорий: {sorted(missing)}"
    for sid, el in symbols.items():
        assert el.get("viewBox") == "0 0 24 24", f"{sid}: без viewBox <use> не масштабируется"
        assert el.get("stroke") == "currentColor", f"{sid}: цвет должен наследоваться (currentColor)"


def test_sprite_offline_and_within_budget():
    raw = SPRITE.read_bytes()
    assert len(raw) <= 12_000, f"бюджет спрайта (≤12 КБ), сейчас {len(raw)}"
    text = raw.decode("utf-8")
    assert "<script" not in text.lower()
    body = text.replace('xmlns="http://www.w3.org/2000/svg"', "")
    assert "http" not in body, "внешние ссылки в спрайте запрещены (офлайн-контур)"
    assert "url(" not in body


def test_cat_icon_resolution_and_fallback():
    """Глобал cat_icon: встроенные категории → свой символ; неизвестный слаг → фолбэк tag (иконка есть всегда)."""
    from spendtrack.cat_icons import cat_icon, icon_name, sprite_icon_names

    assert "#i-groceries" in str(cat_icon("groceries"))
    assert 'aria-hidden="true"' in str(cat_icon("groceries"))
    assert icon_name("какая-то-нетипичная") == "tag"
    assert "#i-tag" in str(cat_icon("какая-то-нетипичная"))
    assert "#i-tag" in str(cat_icon(""))  # пустой слаг безопасен
    names = sprite_icon_names()
    assert "tag" in names and "paw" in names and "gift" in names  # банк кастомных иконок
    assert len(names) >= 30


def test_pages_render_category_icons(tmp_path, monkeypatch):
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "icons.db"))
    with TestClient(app) as client:
        r = client.post("/api/transactions",
                        json={"date": "2026-09-12", "description": "ЛЕНТА", "amount": "-100.00"})
        assert r.status_code == 200
        index = client.get("/").text
        assert "cat-icons.svg" in index and "#i-groceries" in index
        assert '<svg class="cat-icon' in index

        store = Store(db_path=tmp_path / "icons.db")
        try:
            store.set_budget("groceries", 100_000)
        finally:
            store.close()
        dash = client.get("/dashboard").text
        assert "#i-groceries" in dash  # чип бюджета + строка «Итоги по категориям»
        assert 'style="color:' in dash  # иконка окрашена цветом категории


def _file_hash(html: str) -> str:
    import re

    m = re.search(r'name="file_hash" value="([0-9a-f]{64})"', html)
    assert m, "file_hash не найден в разметке настроек"
    return m.group(1)


def test_custom_category_icon_flow(tmp_path, monkeypatch):
    """Кастомная категория: иконка выбирается при создании и меняется в настройках (автосохранение)."""
    import re

    tax = tmp_path / "taxonomy.toml"
    tax.write_text((ROOT / "config" / "taxonomy.toml").read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv("SPENDTRACK_TAXONOMY", str(tax))
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "ti.db"))
    with TestClient(app) as client:
        # Пикер настроек предлагает банк иконок спрайта
        settings_html = client.get("/settings").text
        icon_options = set(re.findall(r'<option value="([a-z0-9-]+)"[^>]*>(?:[a-z0-9-]+)</option>',
                                      settings_html))
        from spendtrack.cat_icons import sprite_icon_names

        assert set(sprite_icon_names()) >= {"tag", "paw", "star"}
        assert "paw" in settings_html and icon_options

        # Создание категории с выбранной иконкой
        r = client.post("/settings/categories",
                        data={"name": "pet", "color": "#7c3aed", "icon": "paw",
                              "file_hash": _file_hash(client.get("/settings").text)})
        assert r.status_code == 200 and "pet" in r.text

        store = Store(db_path=tmp_path / "ti.db")
        try:
            store.add_transaction(date="2026-09-10", description="КОРМ", amount_kopecks=-100,
                                  category="pet", category_source="manual")
        finally:
            store.close()
        assert "#i-paw" in client.get("/?month=2026-09").text  # иконка доехала до списка

        # Смена иконки — автосохранением
        r2 = client.post("/settings/categories/icon",
                         data={"name": "pet", "icon": "star", "file_hash": _file_hash(r.text)})
        assert r2.status_code == 200 and "#i-star" in r2.text
        assert "#i-star" in client.get("/?month=2026-09").text

        # Неизвестная иконка — вежливая ошибка, файл не портится
        r3 = client.post("/settings/categories/icon",
                         data={"name": "pet", "icon": "нет-такой", "file_hash": _file_hash(r2.text)})
        assert "неизвестная иконка" in r3.text
