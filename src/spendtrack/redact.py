"""Egress-redaction: маскирование PII перед отправкой в LLM.

Зачем: в `build_user_prompt` уходят `description` и `merchant` из банковской выписки.
В описаниях регулярно встречаются номера карт/счетов, телефоны и e-mail (переводы, оплата
услуг). Для категоризации они не нужны — это лишний egress (PRIVACY.md, принцип «минимум
данных»). Маскирование выполняется на единственном шлюзе payload-билдера (`prompts.py`),
поэтому не зависит от того, какой провайдер выбран.

Инварианты:
* суммы, даты и обычный текст мерчанта не меняются (иначе падает качество классификации);
* выключение — env `SPENDTRACK_LLM_REDACT=0` (осознанный opt-out; например, полностью
  локальный Ollama без выхода в сеть). Для удалённых провайдеров `call_llm` принудительно
  прогоняет payload через `redact`, даже если builder вызван с opt-out;
* замена детерминированная и идемпотентная (повторный прогон не портит текст).
"""
from __future__ import annotations

import os
import re

CARD = "[CARD]"
PHONE = "[PHONE]"
EMAIL = "[EMAIL]"
IBAN = "[IBAN]"

# Горизонтальные разделители из выписок: обычный/неразрывный/узкий/тонкий пробел, дефис.
_HSPACE = r"[ \t\u00a0\u2007\u2009\u202f]"
# Один класс вместо вложенных `space*[-]?space*`: меньше backtracking на длинных описаниях.
_PHONE_SEP = r"[ \t\u00a0\u2007\u2009\u202f()\-]*"
_DIGIT_SEP = r"[ \t\u00a0\u2007\u2009\u202f\-]*"

# E-mail — до остальных правил: внутри него бывают цифры.
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")

# РФ-счёт: ровно 20 цифр, в т.ч. слитно или группами (40817 810 0 9991 0004312).
# Держим ДО карт/телефонов: иначе 13–19-значный хвост с пробелом мог маскироваться как карта.
# Маркер — существующий `[CARD]` (PRIVACY.md: карточные и счётные номера), без нового контракта.
_ACCOUNT_RE = re.compile(rf"(?<!\d)(?:\d{_DIGIT_SEP}){{19}}\d(?!\d)")

# Телефоны: РФ (+7/8/7 без плюса/9XXXXXXXXX) и международный формат (+375 29 123-45-67).
# Вариант «9…» — 10 цифр без префикса; он же покрывает 916… из выписок.
_PHONE_RE = re.compile(
    rf"(?<![\d+])"
    rf"(?:\+\d{{1,3}}{_PHONE_SEP}\d{{2,4}}{_PHONE_SEP}\d{{3}}{_PHONE_SEP}\d{{2}}{_PHONE_SEP}\d{{2}}"
    rf"|8{_PHONE_SEP}\d{{3}}{_PHONE_SEP}\d{{3}}{_PHONE_SEP}\d{{2}}{_PHONE_SEP}\d{{2}}"
    rf"|7{_PHONE_SEP}9\d{{2}}{_PHONE_SEP}\d{{3}}{_PHONE_SEP}\d{{2}}{_PHONE_SEP}\d{{2}}"
    rf"|9{_PHONE_SEP}\d{{3}}{_PHONE_SEP}\d{{3}}{_PHONE_SEP}\d{{2}}{_PHONE_SEP}\d{{2}}"
    rf"|9\d{{2}}{_PHONE_SEP}\d{{3}}{_PHONE_SEP}\d{{2}}{_PHONE_SEP}\d{{2}}"
    rf"|8\d{{9}})(?!\d)"
)

# IBAN/счёт: 2 буквы + 2 цифры + 10–30 буквенно-цифровых, в т.ч. группами по 4.
# Регистр не важен: выписки встречаются и в нижнем регистре; NBSP — тот же пробел.
_IBAN_SPACED_RE = re.compile(
    rf"\b[A-Z]{{2}}\d{{2}}(?:{_HSPACE}?[A-Z0-9]{{4}}){{2,7}}\b", re.IGNORECASE)
_IBAN_PLAIN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b", re.IGNORECASE)

# Карты: 13–19 цифр подряд или с пробелами/дефисами/NBSP.
_CARD_GROUPED_RE = re.compile(rf"(?<!\d)(?:\d{_DIGIT_SEP}){{12,18}}\d(?!\d)")
_CARD_PLAIN_RE = re.compile(r"(?<!\d)\d{13,19}(?!\d)")

_RULES = (
    (_EMAIL_RE, EMAIL),
    (_IBAN_SPACED_RE, IBAN),
    (_IBAN_PLAIN_RE, IBAN),
    (_ACCOUNT_RE, CARD),
    (_PHONE_RE, PHONE),
    (_CARD_GROUPED_RE, CARD),
    (_CARD_PLAIN_RE, CARD),
)


def redaction_enabled() -> bool:
    """По умолчанию включена; `SPENDTRACK_LLM_REDACT=0` — явный opt-out."""
    return os.environ.get("SPENDTRACK_LLM_REDACT", "1").strip().lower() not in {"0", "false", "no", "off"}


def redact(text: str) -> str:
    """Маскировать карты/счета, телефоны и e-mail. Остальной текст не трогаем."""
    if not text:
        return text
    out = str(text)
    for pattern, token in _RULES:
        out = pattern.sub(token, out)
    return out


def redact_if_enabled(text: str) -> str:
    return redact(text) if redaction_enabled() else text
