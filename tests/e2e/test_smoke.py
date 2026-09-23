from __future__ import annotations

import re
import sqlite3
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from helpers import open_panel, seed_tx
from helpers import seed_pending as _seed_pending
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


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
    open_panel(page, "add")
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
        open_panel(page, "add")
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
    open_panel(page, "import")
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


def test_import_csv_by_file_upload(page: Page, live_server, tmp_path):
    """M-6: CSV-файл из <input type=file> импортируется через multipart (без textarea)."""
    path = tmp_path / "sber.csv"
    path.write_text(
        "Номер документа;Дата операции;Номер карты;Статус;Сумма операции;"
        "Валюта операции;Категория;Описание\n"
        "1;01.09.2026 10:00;1234;Выполнено;-1 234,56;RUB;Продукты;ЛЕНТА ФАЙЛ\n",
        encoding="utf-8")
    page.goto(live_server)
    open_panel(page, "import")
    page.set_input_files('#import-form input[type=file]', str(path))
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
    expect(page.locator("#review-rows")).to_contain_text("Транспорт")

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
    expect(page.locator("#review-1")).to_contain_text("Быт и дом")

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
    expect(page.locator("#dash-month")).to_have_text("Сентябрь 2026")
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
    expect(page.locator("#dash-month")).to_have_text("Август 2026")
    aug = chart_probe()
    assert aug["data"] == [-70.0] and aug["cats"] == [70.0]
    assert abs(aug["h"] - sep["h"]) <= 8  # канвас заполняет контейнер h-56 и не «утекает»

    page.click('a[href="/dashboard?month=2026-09"]')
    _wait_htmx(page, "#dash-month")
    expect(page.locator("#dash-month")).to_have_text("Сентябрь 2026")

    # пустой месяц: чартов нет, но страница/навигация живут
    page.click('a[href="/dashboard?month=2026-10"]')
    _wait_htmx(page, "#dash-month")
    expect(page.locator("#dash-month")).to_have_text("Октябрь 2026")
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
    expect(page.locator("body")).to_contain_text("−199,00 ₽ / мес")
    expect(page.locator("body")).to_contain_text("n=4")
    expect(page.locator("body")).to_contain_text("активных 1")


def test_dashboard_digest_card(page: Page, live_server, db_path):
    """Карточка «Дайджест недели»: итоги окна, топ-категория, near-дубль (даты от today)."""
    today = datetime.now(UTC).date()
    conn = sqlite3.connect(str(db_path))
    for offset, desc, kop, cat in [
        (1, "ЛЕНТА ВЧЕРА", -15000, "groceries"),
        (2, "ЛЕНТА ПОЗАВЧЕРА", -12000, "groceries"),
    ]:
        conn.execute(
            "INSERT INTO transactions(date, description, amount_kopecks, category, category_source,"
            " confidence, created, updated) VALUES(?,?,?,?, 'import', 1.0,"
            " datetime('now'), datetime('now'))",
            ((today - timedelta(days=offset)).isoformat(), desc, kop, cat))
    for desc in ("КОФЕ", "КОФЕ УГЛОВОЕ"):
        conn.execute(
            "INSERT INTO transactions(date, description, amount_kopecks, category, category_source,"
            " confidence, merchant, created, updated) VALUES(?,?,?, 'restaurants', 'import', 1.0,"
            " 'КОФЕ', datetime('now'), datetime('now'))",
            (today.isoformat(), desc, -30000))
    conn.commit()
    conn.close()

    page.goto(f"{live_server}/dashboard")
    card = page.locator("#digest-card")
    expect(card).to_contain_text("Дайджест недели")
    expect(card).to_contain_text("7 дн")
    expect(card).to_contain_text("\u2212270,00 ₽")   # расход окна: -150 -120, знак — часть отображения
    expect(card).to_contain_text("Продукты")
    expect(card).to_contain_text("к прошлому окну")  # дельта словами (M-5)
    expect(card).not_to_contain_text("возможный дубль")  # аномалии — отдельной карточкой

    anomalies = page.locator("#anomalies-card")   # M-5: первый блок дашборда
    expect(anomalies).to_contain_text("возможный дубль")
    expect(anomalies).to_contain_text("КОФЕ")
    expect(anomalies).to_contain_text("Открыть")


def test_approve_all_button(page: Page, live_server, db_path):
    """Пакетное одобрение ≥ 60% (M-4): уверенная уходит, низкоуверенная остаётся человеку."""
    _seed_pending(str(db_path), [
        ("fp-b1", "2026-09-12", "ЛЕНТА А", -3000, 0.7, "groceries"),
        ("fp-b2", "2026-09-13", "Яндекс Такси", -2000, 0.5, "transport"),
    ])

    page.goto(f"{live_server}/approve")
    _wait_htmx(page, "#review-rows")
    expect(page.locator("#review-rows")).to_contain_text("ЛЕНТА А")
    expect(page.locator("#review-rows")).to_contain_text("Яндекс Такси")
    expect(page.locator("#approve-all-wrap button")).to_contain_text("(1)")

    # auto-accept confirm dialog
    page.on("dialog", lambda d: d.accept())
    page.click("#approve-all-wrap button")
    page.wait_for_function("() => window.htmx && !document.querySelector('.htmx-request')")
    expect(page.locator("#review-rows tr.review-row")).to_have_count(1)
    expect(page.locator("#review-rows")).to_contain_text("Яндекс Такси")
    expect(page.locator("#approve-all-wrap button")).to_have_count(0)  # уверенных больше нет


def test_approve_keyboard_triage(page: Page, live_server, db_path):
    """Клавиатурный триаж (M-4): j — выбрать строку, Enter — одобрить, s — пропустить."""
    _seed_pending(str(db_path), [
        ("fp-k1", "2026-09-12", "ЛЕНТА К", -3000, 0.7, "groceries"),
        ("fp-k2", "2026-09-13", "АЗС К", -2000, 0.65, "transport"),
    ])

    page.goto(f"{live_server}/approve")
    _wait_htmx(page, "#review-rows")
    expect(page.locator("#review-rows tr.review-row")).to_have_count(2)

    page.keyboard.press("j")
    expect(page.locator("#review-1")).to_have_class(re.compile(r"is-selected"))
    page.keyboard.press("Enter")  # одобрить первую (как предложено)
    expect(page.locator("#review-1")).to_have_count(0)
    expect(page.locator("#review-rows tr.review-row")).to_have_count(1)
    page.keyboard.press("s")  # пропустить оставшуюся
    _wait_single(page, "#review-rows")
    expect(page.locator("#review-rows")).to_contain_text("Все подтверждены")


def test_approve_empty_queue(page: Page, live_server):
    """Пустая очередь показывает сообщение."""
    page.goto(f"{live_server}/approve")
    _wait_htmx(page, "#review-rows")
    expect(page.locator("#review-rows")).to_contain_text("Все подтверждены")


def test_export_csv_link_downloads(page: Page, live_server, db_path):
    """Кнопка «Экспорт CSV» на главной скачивает файл: BOM + данные текущего фильтра."""
    _seed_pending(str(db_path), [("fp-exp", "2026-09-12", "ЛЕНТА ЭКСПОРТ", -12345, 0.65, "groceries")])
    page.goto(live_server)
    link = page.locator('a[href^="/export.csv"]')
    expect(link).to_have_attribute("aria-label", re.compile("Экспорт"))
    with page.expect_download() as dl:
        link.click()
    download = dl.value
    assert download.suggested_filename.startswith("spend-export-")
    data = download.path().read_bytes()
    assert data.startswith(b"\xef\xbb\xbf")
    assert "ЛЕНТА ЭКСПОРТ" in data.decode("utf-8-sig")


def test_export_xlsx_downloads(page: Page, live_server, db_path):
    """XLSX-выгрузка: файл скачивается и открывается openpyxl (аудит 23.09, P1)."""
    _seed_pending(str(db_path), [("fp-xlsx", "2026-09-12", "ЛЕНТА XLSX", -12345, 0.65, "groceries")])
    page.goto(live_server)
    with page.expect_download() as dl:
        page.evaluate("url => { window.location.href = url }", f"{live_server}/export.xlsx")
    download = dl.value
    assert download.suggested_filename.endswith(".xlsx")
    import io

    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(download.path().read_bytes()))
    values = [cell for row in workbook.active.values for cell in row if isinstance(cell, str)]
    assert any("ЛЕНТА XLSX" in value for value in values)


def test_currency_in_list_day_total_rub_only(page: Page, live_server, db_path):
    """Мультивалютность в UI: не-RUB с кодом и не попадает в ₽-итог дня (аудит 23.09, P1)."""
    seed_tx(str(db_path), "2026-09-12", "ЛЕНТА РУБ", -10000)
    seed_tx(str(db_path), "2026-09-12", "AMAZON USD", -50000, currency="USD")

    page.goto(live_server)
    table = page.locator("#tx-table")
    expect(table).to_contain_text("−500,00 USD")
    expect(table).to_contain_text("итог −100,00 ₽")
    expect(table).not_to_contain_text("итог −600,00")


def test_help_page_nav_and_faq(page: Page, live_server):
    """Помощь: ссылка в меню ведёт на /help, FAQ-вопрос раскрывается (нативные details)."""
    page.goto(live_server)
    page.click('nav a[href="/help"]')
    expect(page.locator("h1")).to_have_text("Помощь")
    expect(page.locator("#quick-start")).to_be_visible()
    page.locator("#faq-import-duplicates summary").click()
    expect(page.locator("#faq-import-duplicates")).to_contain_text("повторный импорт")