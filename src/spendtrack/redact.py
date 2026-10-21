"""Egress-redaction: маскирование PII перед отправкой в LLM.

Зачем: в `build_user_prompt` уходят `description` и `merchant` из банковской выписки.
В описаниях регулярно встречаются номера карт/счетов, телефоны и e-mail (переводы, оплата
услуг). Для категоризации они не нужны — это лишний egress (PRIVACY.md, принцип «минимум
данных»). Маскирование выполняется на единственном шлюзе payload-билдера (`prompts.py`),
поэтому не зависит от того, какой провайдер выбран.

Инварианты:
* суммы, даты и обычный текст мерчанта не меняются (иначе падает качество классификации);
* выключение — env `SPENDTRACK_LLM_REDACT=0` (осознанный opt-out; например, полностью
  локальный Ollama без выхода в сеть);
* замена детерминированная и идемпотентная (повторный прогон не портит текст).
"""
from __future__ import annotations

import os
import re

CARD = "[CARD]"
PHONE = "[PHONE]"
EMAIL = "[EMAIL]"
IBAN = "[IBAN]"

# E-mail — до остальных правил: внутри него бывают цифры.
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")

# Телефоны: РФ (+7/8) и международный формат (+375 29 123-45-67) с разделителями.
_PHONE_RE = re.compile(
    r"(?<![\d+])(?:\+\d{1,3}[\s\-()]*\d{2,4}[\s\-()]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}"
    r"|8[\s\-()]*\d{3}[\s\-()]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2})(?!\d)"
)

# IBAN/счёт: 2 буквы + 2 цифры + 10–30 буквенно-цифровых, в т.ч. группами по 4.
_IBAN_SPACED_RE = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}\b")
_IBAN_PLAIN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")

# Карты/счета: 13–19 цифр подряд или с пробелами/дефисами.
_CARD_GROUPED_RE = re.compile(r"(?<!\d)(?:\d[ \-]?){12,18}\d(?!\d)")
_CARD_PLAIN_RE = re.compile(r"(?<!\d)\d{13,19}(?!\d)")

_RULES = (
    (_EMAIL_RE, EMAIL),
    (_PHONE_RE, PHONE),
    (_IBAN_SPACED_RE, IBAN),
    (_IBAN_PLAIN_RE, IBAN),
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
