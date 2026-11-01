"""E2E: mobile capture page in a real browser (temp server, loopback)."""
from __future__ import annotations

import os
import sqlite3

import pytest

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="session", autouse=True)
def _require_chromium() -> None:
    """Skip gracefully on machines/CI without a Playwright browser binary."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            browser.close()
    except Exception as exc:  # noqa: BLE001 — отсутствие браузера не должно красить unit-контур
        message = f"Playwright chromium unavailable: {exc}"
        if os.environ.get("CI"):
            pytest.fail(f"{message}; CI e2e job must install chromium")
        pytest.skip(message)


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
