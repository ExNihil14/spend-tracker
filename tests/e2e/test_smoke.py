from __future__ import annotations

import re
import sqlite3
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def _seed_pending(conn_str: str, rows: list[tuple]) -> None:
    """Засеять pending-транзакции напрямую в БД (обход LLM): (fp, date, desc, sum, conf, llm_cat)."""
    conn = sqlite3.connect(conn_str)
    for fp, day, desc, amount_kopecks, conf, llm_cat in rows:
        conn.execute(
            """INSERT INTO transactions
               (fingerprint, date, description, amount_kopecks, category,
                category_source, confidence, category_llm, review_status,
                created, updated)
               VALUES (?, ?, ?, ?, 'other', 'llm_pending_review', ?, ?, 'pending',
                       datetime('now'), datetime('now'))""",
            (fp, day, desc, amount_kopecks, conf, llm_cat),
        )
    conn.commit()
    conn.close()


def _wait_htmx(page: Page, selector: str, timeout: int = 15_000) -> None:
    """Ждём завершения htmx-запроса и появления контента в целевом элементе."""
    page.wait_for_function(
        "() => window.htmx && !document.querySelector('.htmx-request')",
        timeout=timeout,
    )
    expect(page.locator(selector).first).not_to_be_empty(timeout=timeout)


def _wait_single(page: Page, selector: str, timeout: int = 15_000) -> None:
    """Ждём, пока htmx завершит swap (settling) и останется ровно один элемент."""
    page.wait_for_function(
        "(sel) => window.htmx && !document.querySelector('.htmx-request')"
        " && document.querySelectorAll(sel).length === 1",
        arg=selector,
        timeout=timeout,
    )


def test_add_transaction_rule_keyword(page: Page, live_server):
    """Добавление через UI: «ЛЕНТА» матчится keyword-правилом → groceries без LLM."""
    page.goto(live_server)
    page.fill('input[name="date"]', "2026-09-12")
    page.fill('input[name="description"]', "ЛЕНТА")
    page.fill('input[name="amount"]', "-1234.56")
    page.click('form[hx-post="/api/transactions"] button')
    _wait_htmx(page, "#newmsg")
    expect(page.locator("#newmsg").first).to_contain_text(re.compile(r"добавлен|ok", re.IGNORECASE))
    # refresh-list from:body должен перерисовать таблицу
    expect(page.locator("#tx-table")).to_contain_text("ЛЕНТА")


def test_filter_search_htmx(page: Page, live_server):
    """Поиск по q: htmx-фильтр запрашивает новую таблицу."""
    marker = f"ЛЕНТА{uuid4().hex[:6]}"
    with page.expect_response(lambda r: "/api/transactions" in r.url and r.request.method == "POST"):
        page.goto(live_server)
        page.fill('input[name="date"]', "2026-09-12")
        page.fill('input[name="description"]', marker)
        page.fill('input[name="amount"]', "-100.00")
        page.click('form[hx-post="/api/transactions"] button')
    _wait_htmx(page, "#newmsg")
    expect(page.locator("#tx-table")).to_contain_text(marker)
    # теперь поиск: уникальный мерчант → RSS только его
    page.fill('input[name="q"]', marker)
    _wait_htmx(page, "#tx-table")
    expect(page.locator("#tx-table")).to_contain_text(marker)


def test_import_csv_via_ui(page: Page, live_server):
    """Импорт Сбер-CSV через UI: выбран банк, вставлены строки, фрагмент в #importmsg."""
    page.goto(live_server)
    csv = (
        "Номер документа;Дата операции;Номер карты;Статус;Сумма операции;"
        "Валюта операции;Категория;Описание\n"
        "1;01.09.2026 10:00;1234;Выполнено;-1 234,56;RUB;Продукты;ЛЕНТА\n"
    )
    page.select_option('select[name="bank"]', "sber")
    page.fill('textarea[name="csv"]', csv)
    page.click('form[hx-post="/api/import"] button')
    _wait_htmx(page, "#importmsg")
    expect(page.locator("#importmsg").first).to_contain_text(re.compile(r"добавлено", re.IGNORECASE))


def test_health_endpoint(page: Page, live_server):
    """/health отвечает JSON-статусом на живом сервере."""
    page.goto(f"{live_server}/health")
    expect(page.locator("body")).to_contain_text('"status"')


def test_picker_inputs_have_pointer_cursor(page: Page, live_server):
    """Нативные пикеры: курсор-указатель на поле + тёмная схема для popup (регрессия Tailwind preflight)."""
    page.goto(live_server)
    assert page.eval_on_selector('input[name="date"]',
                                 "el => getComputedStyle(el).cursor") == "pointer"
    assert page.evaluate("getComputedStyle(document.documentElement).colorScheme") == "dark"
    page.goto(f"{live_server}/settings")
    assert page.eval_on_selector('input[type="color"]',
                                 "el => getComputedStyle(el).cursor") == "pointer"


# ── Approve-очередь ─────────────────────────────────────────────────────────

def test_approve_queue_skip(page: Page, live_server, db_path):
    """Пропуск pending-транзакции удаляет строку из очереди."""
    _seed_pending(str(db_path), [("fp-skip", "2026-09-12", "АЗС ЛУКОЙЛ", -15000, 0.65, "transport")])

    page.goto(f"{live_server}/approve")
    _wait_htmx(page, "#review-rows")
    expect(page.locator("#review-rows")).to_contain_text("АЗС ЛУКОЙЛ")
    expect(page.locator("#review-rows")).to_contain_text("transport")

    page.locator("#review-1 button:has-text('Пропустить')").click()
    _wait_single(page, "#review-rows")
    expect(page.locator("#review-rows")).to_contain_text("Все подтверждены")


def test_approve_queue_approve_with_category(page: Page, live_server, db_path):
    """Выбор другой категории + «Одобрить» — транзакция уходит из очереди."""
    _seed_pending(str(db_path), [
        ("fp-a1", "2026-09-12", "КАФЕ МОЛОКО",  -5000, 0.55, "food"),
        ("fp-a2", "2026-09-13", "АЗС ЛУКОЙЛ",  -15000, 0.65, "transport"),
    ])

    page.goto(f"{live_server}/approve")
    _wait_htmx(page, "#review-rows")
    expect(page.locator("#review-1")).to_contain_text("КАФЕ МОЛОКО")

    # одобряем первую: выбираем другую категорию и жмём «Одобрить»
    page.locator("#review-1 select[name='category']").select_option("groceries")
    page.locator("#review-1 button:has-text('Одобрить')").click()
    _wait_single(page, "#review-rows")
    expect(page.locator("#review-1")).to_have_count(0)
    expect(page.locator("#review-2")).to_contain_text("АЗС ЛУКОЙЛ")


def test_approve_queue_approve_as_proposed(page: Page, live_server, db_path):
    """«Одобрить» без смены select принимает предложенную LLM категорию."""
    _seed_pending(str(db_path), [
        ("fp-p1", "2026-09-12", "СТРОЙКАОПТ МСК", -5000, 0.55, "household"),
    ])

    page.goto(f"{live_server}/approve")
    _wait_htmx(page, "#review-rows")
    expect(page.locator("#review-1")).to_contain_text("household")

    page.locator("#review-1 button:has-text('Одобрить')").click()
    _wait_single(page, "#review-rows")
    expect(page.locator("#review-rows")).to_contain_text("Все подтверждены")
    expect(page.locator("#approve-all-wrap button")).to_have_count(0)
    expect(page.locator("#toast")).to_contain_text("Одобрено")


def test_dashboard_month_nav_and_chart_scale(page: Page, live_server, db_path):
    """Стрелки — абсолютный переход по месяцам; ось Y в рублях; график не «утекает» при перерисовке."""
    conn = sqlite3.connect(str(db_path))
    for fp_date, desc, kop in [
        ("2026-08-10", "ЛЕНТА АВГ", -7000),    # -70.00 ₽
        ("2026-09-10", "ЛЕНТА СЕН", -15000),   # -150.00 ₽
    ]:
        conn.execute(
            "INSERT INTO transactions(date, description, amount_kopecks, category, category_source,"
            " confidence, created, updated) VALUES(?,?,?, 'groceries', 'rule', 1.0,"
            " datetime('now'), datetime('now'))", (fp_date, desc, kop))
    conn.commit()
    conn.close()

    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.goto(f"{live_server}/dashboard")
    expect(page.locator("#dash-month")).to_have_text("2026-09")
    # стрелки ведут на АБСОЛЮТНЫЙ месяц — можно листать вглубь истории
    expect(page.locator('a[href="/dashboard?month=2026-08"]')).to_have_count(1)
    expect(page.locator('a[href="/dashboard?month=2026-10"]')).to_have_count(1)

    def chart_probe() -> dict:
        page.wait_for_function(
            "() => { const c = window.Chart && Chart.getChart(document.getElementById('dailyChart'));"
            " return c && c.data.datasets[0].data.length > 0; }",
            timeout=8_000)
        return page.evaluate(
            """() => {
                 const el = document.getElementById('dailyChart');
                 const c = Chart.getChart(el);
                 const cats = window.Chart.getChart(document.getElementById('catsChart'));
                 return { data: c.data.datasets[0].data,
                          tick: c.options.scales.y.ticks.callback(-70),
                          h: Math.round(el.getBoundingClientRect().height),
                          cats: cats ? cats.data.datasets[0].data : null };
               }""")

    sep = chart_probe()
    assert sep["data"] == [-150.0]        # сентябрь: -150 ₽ (не -1.50 и не -15000)
    assert sep["tick"] == "-70.00 ₽"      # ось в рублях, без двойного деления на 100
    assert sep["cats"] == [150.0]         # doughnut: расходы положительные, тоже в рублях

    page.click('a[href="/dashboard?month=2026-08"]')
    _wait_htmx(page, "#dash-month")
    expect(page.locator("#dash-month")).to_have_text("2026-08")
    aug = chart_probe()
    assert aug["data"] == [-70.0] and aug["cats"] == [70.0]
    assert abs(aug["h"] - sep["h"]) <= 8  # канвас заполняет контейнер h-56 и не «утекает»

    page.click('a[href="/dashboard?month=2026-09"]')
    _wait_htmx(page, "#dash-month")
    expect(page.locator("#dash-month")).to_have_text("2026-09")

    # пустой месяц: чартов нет, но страница/навигация живут
    page.click('a[href="/dashboard?month=2026-10"]')
    _wait_htmx(page, "#dash-month")
    expect(page.locator("#dash-month")).to_have_text("2026-10")
    assert page.evaluate(
        "() => { const el = document.getElementById('dailyChart');"
        " return !!(el && window.Chart && Chart.getChart(el)); }") is False
    expect(page.locator('a[href="/dashboard?month=2026-09"]')).to_have_count(1)
    assert not errors, errors

    # индекс: те же стрелки — тоже абсолютные (тот же баг-класс)
    page.goto(f"{live_server}/")
    expect(page.locator('a[href="/?month=2026-08"]')).to_have_count(1)


def test_dashboard_charts_render_via_boost(page: Page, live_server, db_path):
    """Графики /dashboard рендерятся и при переходе через hx-boost (не только прямым заходом)."""
    _seed_pending(str(db_path), [
        ("fp-chart", "2026-09-12", "АЗС ЛУКОЙЛ", -15000, 0.65, "fuel"),
    ])

    page.goto(live_server)
    page.click("a[href='/dashboard']")
    expect(page.locator("#dailyChart")).to_be_visible()
    page.wait_for_function(
        "() => window.Chart && !!Chart.getChart(document.getElementById('dailyChart'))",
        timeout=10_000,
    )


def test_dashboard_recurring_card(page: Page, live_server, db_path):
    """Карточка «Подписки»: синтетика 4×30 дней → мерчант, цена, месячный итог (даты от today)."""
    page.goto(f"{live_server}/dashboard")
    expect(page.locator("body")).not_to_contain_text("Подписки / рекурринги")

    today = datetime.now(UTC).date()
    conn = sqlite3.connect(str(db_path))
    for i in (3, 2, 1, 0):
        day = (today - timedelta(days=30 * i)).isoformat()
        conn.execute(
            "INSERT INTO transactions(date, description, amount_kopecks, category, category_source,"
            " confidence, merchant, created, updated)"
            " VALUES(?, 'NETFLIX.COM', -19900, 'subscriptions', 'import', 1.0, 'NETFLIX',"
            " datetime('now'), datetime('now'))", (day,))
    conn.commit()
    conn.close()

    page.goto(f"{live_server}/dashboard")
    expect(page.locator("body")).to_contain_text("Подписки / рекурринги")
    expect(page.locator("body")).to_contain_text("NETFLIX")
    expect(page.locator("body")).to_contain_text("199.00 ₽ / мес")
    expect(page.locator("body")).to_contain_text("n=4")
    expect(page.locator("body")).to_contain_text("активных 1")


def test_approve_all_button(page: Page, live_server, db_path):
    """Кнопка «Одобрить все» убирает все pending-строки."""
    _seed_pending(str(db_path), [
        ("fp-b1", "2026-09-12", "ЛЕНТА А", -3000, 0.7, "groceries"),
        ("fp-b2", "2026-09-13", "Яндекс Такси", -2000, 0.5, "transport"),
    ])

    page.goto(f"{live_server}/approve")
    _wait_htmx(page, "#review-rows")
    expect(page.locator("#review-rows")).to_contain_text("ЛЕНТА А")
    expect(page.locator("#review-rows")).to_contain_text("Яндекс Такси")

    # auto-accept confirm dialog
    page.on("dialog", lambda d: d.accept())
    page.click("button:has-text('Одобрить все')")
    _wait_single(page, "#review-rows")
    expect(page.locator("#review-rows")).to_contain_text("Все подтверждены")


def test_approve_empty_queue(page: Page, live_server):
    """Пустая очередь показывает сообщение."""
    page.goto(f"{live_server}/approve")
    _wait_htmx(page, "#review-rows")
    expect(page.locator("#review-rows")).to_contain_text("Все подтверждены")