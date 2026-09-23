"""Регресс-защита ожидания htmx-settle в e2e-хелперах (флейк CI 16.09→20.09).

Контекст: после AJAX-swap htmx снимает `.htmx-request` СРАЗУ (в onload), а новый контент
получает обработчики только в settle (`defaultSettleDelay=20ms`: `makeAjaxLoadTask` →
`processNode`), маркер незрелого контента — класс `htmx-added`. Если тест взаимодействует
в этом окне, input-событие теряется (у элемента ещё нет слушателей) и baseline `changed`
фиксируется на «уже введённом» значении — повторный fill считается «не changed» и
превью-запрос не уходит вовсе (наблюдалось: 0 htmx:trigger, 0 сетевых запросов).

Этот тест доказывает окно детерминированно: input в окне вставка..settle игнорируется,
а тот же input после снятия `htmx-added` — обрабатывается. Если тест упал после
обновления htmx — перепроверить `_wait_single` в test_settings_e2e.py (условие
`!document.querySelector('.htmx-added')`).
"""
from __future__ import annotations

from urllib.parse import parse_qs

import pytest
from playwright.sync_api import Page

pytestmark = pytest.mark.e2e

PATTERN_INPUT = '#settings-rules input[name="pattern"]'

SETTLE_WINDOW_JS = """
var obs = new MutationObserver(function (records) {
  records.forEach(function (r) {
    r.addedNodes.forEach(function (n) {
      if (n.id !== 'settings-rules' || !n.classList.contains('htmx-added')) return;
      var inp = n.querySelector('input[name=pattern]');
      inp.value = 'ОКНО SETTLE';
      inp.dispatchEvent(new Event('input', {bubbles: true}));
      var attr = new MutationObserver(function () {
        if (n.classList.contains('htmx-added')) return;
        attr.disconnect();
        var inp2 = n.querySelector('input[name=pattern]');
        inp2.value = 'ПОСЛЕ SETTLE';
        inp2.dispatchEvent(new Event('input', {bubbles: true}));
      });
      attr.observe(n, {attributes: true, attributeFilter: ['class']});
    });
  });
});
obs.observe(document.body, {childList: true, subtree: true});
"""


def test_htmx_settle_window_input_is_ignored(page: Page, live_server) -> None:
    requests: list[str] = []
    page.on(
        "request",
        lambda r: requests.append(r.post_data or "")
        if "/settings/rules/preview" in r.url
        else None,
    )
    page.goto(f"{live_server}/settings")
    page.evaluate(SETTLE_WINDOW_JS)

    def _settle_preview(response) -> bool:
        if "/settings/rules/preview" not in response.url:
            return False
        body = response.request.post_data or ""
        return parse_qs(body).get("pattern", [""])[0] == "ПОСЛЕ SETTLE"

    page.fill(PATTERN_INPUT, "ЭТАЛОН ПРАВИЛО")
    page.select_option('#settings-rules select[name="category"]', "other")
    with page.expect_response(_settle_preview):  # детерминированно, без фикс-паузы 1500 мс
        page.click('#settings-rules form[hx-post="/settings/rules"] button[type="submit"]')

    patterns = [parse_qs(body).get("pattern", [""])[0] for body in requests]
    assert "ОКНО SETTLE" not in patterns
    assert patterns.count("ПОСЛЕ SETTLE") == 1
