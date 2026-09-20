"""Страница помощи /help — структура, легенда, FAQ и ссылка в навигации (оффлайн).

Контент/структура — по ресёрчу `D:\\dev\\docs\\machine\\RESEARCH_HELP_FAQ_BEST_PRACTICES.md`
(разделы Diátaxis, нативные `<details>`, легенда не только цветом).
"""
from __future__ import annotations

from fastapi.testclient import TestClient

ANCHORS = ("quick-start", "how-to", "glossary", "legend", "faq", "privacy", "why", "links")


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "help.db"))
    from spendtrack.main import app

    return TestClient(app)


def test_help_page_renders_all_sections(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        r = client.get("/help")
        assert r.status_code == 200
        html = r.text
        for anchor in ANCHORS:
            assert f'id="{anchor}"' in html, anchor
        assert "<h1" in html and "Помощь" in html


def test_help_page_faq_glossary_and_legend(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        html = client.get("/help").text
        # FAQ + «Почему так?» — нативные details (без JS), не меньше 24 блоков
        assert html.count("<details") >= 24
        # глоссарий: ключевые термины
        for term in ("Отпечаток", "Уверенность", "Перевод", "рекурринг", "Бюджет"):
            assert term in html, ascii(term)
        # легенда источников категории
        for source in ("rule", "llm", "llm_pending_review", "import", "manual", "correction"):
            assert source in html, source
        # порог авто-приёма рендерится из конфига (не хардкод в шаблоне):
        # ожидание берём из того же конфига, чтобы тест не ломался при смене значения
        from spendtrack.config import load_settings

        threshold = load_settings().acceptance.auto_accept_confidence
        assert str(threshold) in html


def test_help_link_present_in_nav_on_all_pages(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        for path in ("/", "/dashboard", "/approve", "/settings", "/help"):
            html = client.get(path).text
            assert 'href="/help"' in html, path
