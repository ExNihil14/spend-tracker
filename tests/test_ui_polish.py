"""P2 UX-полировка: обучающие пустые состояния, микро-подсказки, знаки сумм (оффлайн, TestClient).

DoD POLISH_PLAN #7-#9: тексты по `RESEARCH_HELP_FAQ_BEST_PRACTICES.md` (§4, §6),
знак суммы — не только цветом (WCAG 1.4.1), ссылки ведут на существующие якоря /help.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from spendtrack.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "ui.db"))
    return TestClient(app)


def _add(client: TestClient, amount: str, desc: str = "ЛЕНТА", date: str = "2026-09-12"):
    r = client.post("/api/transactions", json={"date": date, "description": desc, "amount": amount})
    assert r.status_code == 200


def test_empty_list_teaches_first_step(client):
    html = client.get("/").text
    assert "Пока нет транзакций" in html
    assert 'href="/help#faq-import-sber"' in html


def test_empty_queue_hint_links_to_help(client):
    html = client.get("/approve").text
    assert "Все подтверждены" in html
    assert 'href="/help#faq-queue-why"' in html


def test_dashboard_onboarding_when_no_data(client):
    html = client.get("/dashboard").text
    assert 'id="onboarding"' in html
    assert 'href="/#import"' in html and 'href="/approve"' in html
    assert 'href="/help#quick-start"' in html
    assert "Расходы по дням" not in html  # вместо пустых графиков — онбординг


def test_amounts_render_with_explicit_signs_and_adaptive_badges(client):
    _add(client, "-1234.56", "ЛЕНТА")
    _add(client, "250000.00", "ЗАРАБОТНАЯ ПЛАТА")
    html = client.get("/").text
    assert "\u22121234.56" in html          # U+2212 у расхода
    assert "+250000.00" in html             # явный плюс у дохода
    assert "background:#22c55e;color:#020617" in html  # светлый бейдж groceries → тёмный текст


def test_import_hint_and_help_anchors_exist(client):
    index = client.get("/").text
    assert "повторный импорт не создаёт дублей" in index
    assert 'href="/help#faq-import-sber"' in index
    approve = client.get("/approve").text
    assert 'href="/help#faq-queue-why"' in approve
    help_html = client.get("/help").text
    for anchor in ("faq-import-sber", "faq-queue-why", "quick-start"):
        assert f'id="{anchor}"' in help_html, anchor


def test_filtered_empty_state(client):
    _add(client, "-50.00")
    html = client.get("/?category=household").text
    assert "Ничего не найдено по этому фильтру" in html
    assert "Сбросить фильтры" in html


def test_empty_month_state(client):
    _add(client, "-50.00", date="2026-09-12")
    html = client.get("/?month=2026-01").text
    assert "За 2026-01 операций нет" in html
