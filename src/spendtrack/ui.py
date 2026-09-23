"""Общие UI-фрагменты htmx-ответов: OOB-элементы, не зависящие от домена."""
from __future__ import annotations

from html import escape


def oob_toast(text: str) -> str:
    """OOB-тост с подтверждением действия (aria-live; авто-скрытие — скрипт в base.html).

    Заменяет `#toast` (outerHTML) и несёт `data-flash="1"`: app.js показывает сообщение
    и гасит его через ~1.8 с. Разметка совпадает с базовым `#toast` (токены, не палитра).
    """
    return (
        '<div id="toast" hx-swap-oob="outerHTML" data-flash="1" role="status" aria-live="polite"'
        ' class="fixed bottom-4 right-4 z-50 transition-opacity duration-200 bg-surface-2'
        ' border border-line-strong text-fg-strong text-sm rounded-lg px-4 py-2 shadow-xl">'
        f"{escape(text)}</div>"
    )
