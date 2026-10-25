"""Egress-redaction: маскирование PII перед отправкой в LLM.

Зачем: в `build_user_prompt` уходят `description` и `merchant` из банковской выписки.
В описаниях регулярно встречаются номера карт/счетов, телефоны и e-mail (переводы, оплата
услуг). Для категоризации они не нужны — это лишний egress (PRIVACY.md, принцип «минимум
данных»). Маскирование выполняется на единственном шлюзе payload-билдера (`prompts.py`),
поэтому не зависит от того, какой провайдер выбран.

Инварианты:
* суммы, даты и обычный текст мерчанта не меняются (иначе падает качество классификации);
* выключение — env `SPENDTRACK_LLM_REDACT=0` (осознанный opt-out; например, полностью
  локальный Ollama без выхода в сеть). Для loopback-шимов и удалённых провайдеров `call_llm`
  принудительно прогоняет payload через `redact`, даже если builder вызван с opt-out; для
  недоверенных каналов builder маскирует PII до truncate;
* замена детерминированная и идемпотентная (повторный прогон не портит текст).
"""
from __future__ import annotations

import os
import re

CARD = "[CARD]"
PHONE = "[PHONE]"
EMAIL = "[EMAIL]"
IBAN = "[IBAN]"

# Горизонтальные разделители из выписок: обычный/неразрывный/узкий/тонкий пробел,
# дефисы (включая U+2011), точки, скобки.
_HSPACE = r"[ \t\u00a0\u2007\u2009\u202f]"
_PHONE_SEP = r"[ \t\u00a0\u2007\u2009\u202f().\-\u2011]*"
_DIGIT_SEP = r"[ \t\u00a0\u2007\u2009\u202f.\-\u2011]*"

# E-mail — до остальных правил: внутри него бывают цифры. Unicode local/domain,
# ограниченные длины — против квадратичного поиска на длинных «a.a.a…».
_EMAIL_RE = re.compile(
    r"(?<![\w.+-])[\w.!#$%&'*+/=?^_`{|}~-]{1,64}"
    r"@(?:[\w-]{1,63}\.)+[\w-]{2,63}(?![\w-])",
    re.UNICODE,
)

# РФ-счёт: ровно 20 цифр, в т.ч. слитно или группами (40817 810 0 9991 0004312).
# Держим ДО карт/телефонов: иначе 13–19-значный хвост с пробелом мог маскироваться как карта.
# Маркер — существующий `[CARD]` (PRIVACY.md: карточные и счётные номера), без нового контракта.
_ACCOUNT_RE = re.compile(rf"(?<!\d)(?:\d{_DIGIT_SEP}){{19}}\d(?!\d)")

# Карты: 13–19 цифр подряд или с разделителями. ДО телефонов: иначе `916…` внутри
# 6-6-4 card превращал карту в `411111 [PHONE]`.
_CARD_GROUPED_RE = re.compile(rf"(?<!\d)(?:\d{_DIGIT_SEP}){{12,18}}\d(?!\d)")
_CARD_PLAIN_RE = re.compile(r"(?<!\d)\d{13,19}(?!\d)")

# Телефоны: РФ (+7/8/7/9 без плюса) и международные. `8/9` — 10 цифр;
# `495 123-45-67` — городской; `+44 20 7946 0958` — 4+4 subscriber grouping.
_PHONE_RE = re.compile(
    rf"(?<![\d+])"
    rf"(?:\+\d{{1,3}}(?:{_PHONE_SEP}\d{{2,5}}){{2,4}}"
    rf"|8{_PHONE_SEP}\d{{3}}{_PHONE_SEP}\d{{3}}{_PHONE_SEP}\d{{2}}{_PHONE_SEP}\d{{2}}"
    rf"|7{_PHONE_SEP}9\d{{2}}{_PHONE_SEP}\d{{3}}{_PHONE_SEP}\d{{2}}{_PHONE_SEP}\d{{2}}"
    rf"|9{_PHONE_SEP}\d{{3}}{_PHONE_SEP}\d{{3}}{_PHONE_SEP}\d{{2}}{_PHONE_SEP}\d{{2}}"
    rf"|9\d{{2}}{_PHONE_SEP}\d{{3}}{_PHONE_SEP}\d{{2}}{_PHONE_SEP}\d{{2}}"
    rf"|\d{{3}}{_PHONE_SEP}\d{{3}}{_PHONE_SEP}\d{{2}}{_PHONE_SEP}\d{{2}}"
    rf"|8\d{{9}})(?!\d)"
)

# IBAN: страна + 2 цифры + точная длина страны (15–34), с пробелами/точками
# между символами. Точная длина не даёт «съесть» merchant после IBAN.
_IBAN_LENGTHS = {
    "AL": 28, "AD": 24, "AT": 20, "AZ": 28, "BH": 22, "BY": 28, "BE": 16,
    "BA": 20, "BR": 29, "BG": 22, "CR": 22, "HR": 21, "CY": 28, "CZ": 24,
    "DK": 18, "DO": 28, "EE": 20, "FO": 18, "FI": 18, "FR": 27, "GE": 22,
    "DE": 22, "GI": 23, "GR": 27, "GL": 18, "GT": 28, "HU": 28, "IS": 26,
    "IE": 22, "IL": 23, "IT": 27, "JO": 30, "KZ": 20, "XK": 20, "KW": 30,
    "LV": 21, "LB": 28, "LI": 21, "LT": 20, "LU": 20, "MK": 19, "MT": 31,
    "MR": 27, "MU": 30, "MD": 24, "MC": 27, "ME": 22, "NL": 18, "NO": 15,
    "PK": 24, "PS": 29, "PL": 28, "PT": 25, "QA": 29, "RO": 24, "LC": 32,
    "SM": 27, "ST": 25, "SA": 24, "RS": 22, "SC": 31, "SK": 24, "SI": 19,
    "ES": 24, "SE": 24, "CH": 21, "TL": 23, "TN": 24, "TR": 26, "UA": 29,
    "AE": 23, "GB": 22, "VA": 22, "VG": 24,
}
_IBAN_ALT = "|".join(
    rf"{cc}\d{{2}}(?:{_HSPACE}*[A-Z0-9]){{{n - 4}}}"
    for cc, n in sorted(_IBAN_LENGTHS.items())
)
# Fallback для валидных по форме, но не перечисленных/коротких тестовых IBAN
# (например, BY12 ALFA ... в старом контракте). Exact-country идёт первым.
_IBAN_FALLBACK = rf"[A-Z]{{2}}\d{{2}}(?:{_HSPACE}*[A-Z0-9]){{11,30}}"
_IBAN_RE = re.compile(
    rf"\b(?:{_IBAN_ALT}|{_IBAN_FALLBACK})(?![A-Z0-9])", re.IGNORECASE)

_RULES = (
    (_EMAIL_RE, EMAIL),
    (_IBAN_RE, IBAN),
    (_ACCOUNT_RE, CARD),
    (_CARD_GROUPED_RE, CARD),
    (_CARD_PLAIN_RE, CARD),
    (_PHONE_RE, PHONE),
)

# Даты не должны поставлять цифры для card/account/phone кандидатов.
# Прячем их на время правил и возвращаем ровно в исходном виде.
_DATE_RE = re.compile(
    r"\b(?:\d{4}[-.]\d{2}[-.]\d{2}|\d{2}[-.]\d{2}[-.]\d{4})\b"
)


def redaction_enabled() -> bool:
    """По умолчанию включена; `SPENDTRACK_LLM_REDACT=0` — явный opt-out."""
    return os.environ.get("SPENDTRACK_LLM_REDACT", "1").strip().lower() not in {"0", "false", "no", "off"}


def redact(text: str) -> str:
    """Маскировать карты/счета/IBAN/телефоны/e-mail. Остальной текст не трогаем."""
    if not text:
        return text
    out = str(text)
    dates: list[str] = []

    def hide_date(m):
        dates.append(m.group(0))
        return f"\x00DATE{len(dates) - 1}\x00"

    out = _DATE_RE.sub(hide_date, out)
    for pattern, token in _RULES:
        out = pattern.sub(token, out)
    for i, value in enumerate(dates):
        out = out.replace(f"\x00DATE{i}\x00", value)
    return out


def redact_if_enabled(text: str) -> str:
    return redact(text) if redaction_enabled() else text
