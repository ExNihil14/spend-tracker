"""E2E: mobile capture page in a real browser (temp server, loopback)."""
from __future__ import annotations

import sqlite3

import pytest

pytestmark = pytest.mark.e2e


def test_capture_page_submits_with_hidden_client_id(page, live_server, db_path) -> None:
    page.goto(f"{live_server}/capture", wait_until="load")
    assert page.title() == "Быстрый ввод — Spendtrack"
    client_id = page.input_value("#capture-client-id")
    assert client_id
    page.fill("#capture-amount", "-123,45")
    page.fill("#capture-description", "E2E КОФЕ")
    page.click("#capture-form button[type=submit]")
    page.wait_for_selector("#capture-msg:has-text('Добавлено')", timeout=10_000)

    rows = sqlite3.connect(db_path).execute(
        "SELECT COUNT(*) FROM capture_idempotency WHERE client_id = ?", (client_id,)
    ).fetchone()[0]
    assert rows == 1
    assert page.input_value("#capture-client-id") != client_id  # rotated after success
