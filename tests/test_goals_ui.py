"""Ф1 целей: страница /goals, htmx-фрагменты и JSON-API — публичный интерфейс (оффлайн)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from spendtrack.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "goals.db"))
    return TestClient(app)


def test_goals_page_empty_state(client):
    r = client.get("/goals")
    assert r.status_code == 200
    assert "Пока нет целей" in r.text
    assert "Деньги на счёте не блокируются" in r.text  # честный копирайт «виртуального конверта»


def test_create_goal_json_and_page(client):
    r = client.post("/api/goals", json={"title": "Отпуск", "target": "1000", "due_month": "2027-06"})
    assert r.status_code == 200 and r.json()["id"] == 1
    page = client.get("/goals").text
    assert "Отпуск" in page
    assert 'aria-valuenow="0"' in page
    assert "срок: Июнь 2027" in page


def test_create_goal_form_fragment(client):
    r = client.post("/api/goals", data={"title": "Подушка", "target": "10 000"},
                    headers={"hx-request": "true"})
    assert r.status_code == 200
    assert "Подушка" in r.text and 'id="goals-list"' in r.text


def test_create_goal_validation_errors(client):
    r = client.post("/api/goals", json={"title": "X", "target": "0"})
    assert r.status_code == 422
    r2 = client.post("/api/goals", data={"title": " ", "target": "100"},
                     headers={"hx-request": "true"})
    assert r2.status_code == 200 and "text-danger" in r2.text


def test_allocate_updates_progress_and_journal(client):
    client.post("/api/goals", json={"title": "Цель", "target": "1000"})
    r = client.post("/api/goals/1/allocate", data={"amount": "300", "date": "2026-09-10"},
                    headers={"hx-request": "true"})
    assert r.status_code == 200
    assert 'aria-valuenow="30"' in r.text
    assert "300,00" in r.text  # взнос виден в журнале
    # изъятие уменьшает прогресс (подписанные копейки)
    r2 = client.post("/api/goals/1/allocate", data={"amount": "-100", "date": "2026-09-11"},
                     headers={"hx-request": "true"})
    assert 'aria-valuenow="20"' in r2.text


def test_allocate_validation_red_fragment(client):
    client.post("/api/goals", json={"title": "Цель", "target": "1000"})
    r = client.post("/api/goals/1/allocate", data={"amount": "0"}, headers={"hx-request": "true"})
    assert r.status_code == 200 and "text-danger" in r.text


def test_archive_hides_active_forms(client):
    client.post("/api/goals", json={"title": "Старая", "target": "1000"})
    r = client.post("/api/goals/1/archive", headers={"hx-request": "true"})
    assert r.status_code == 200 and "Архив (1)" in r.text
    page = client.get("/goals").text
    assert "Старая" in page  # видна в архиве
    assert "/api/goals/1/allocate" not in page  # но формы взноса у неё больше нет
