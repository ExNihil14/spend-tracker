"""Egress-redaction: PII не уходит в LLM (privacy pack 21.10).

Контракт:
* маскируются карточные/счётные номера, телефоны, e-mail в `description`/`merchant` и в few-shot;
* обычный текст и короткие числа (суммы, «LENTA 5») не трогаются — иначе категоризация деградирует;
* выключение — `SPENDTRACK_LLM_REDACT=0` (осознанный opt-out, напр. полностью локальный Ollama);
* redaction не меняет сигнатуры `build_user_prompt/build_system_prompt` и форму JSON-ответа.
"""
from __future__ import annotations

from spendtrack import prompts
from spendtrack.redact import redact
from spendtrack.taxonomy import load_taxonomy


def test_redact_card_numbers():
    for raw in ("4276 1234 5678 9010", "4276-1234-5678-9010", "4276123456789010"):
        out = redact(raw)
        assert "[CARD]" in out
        assert "4276" not in out and "9010" not in out


def test_redact_phone_russian_formats():
    for raw in ("+7 (999) 123-45-67", "8 999 123 45 67", "+79991234567"):
        out = redact(raw)
        assert "[PHONE]" in out
        assert "999" not in out


def test_redact_email():
    out = redact("ПЕРЕВОД IVAN.PETROV@EXAMPLE.COM")
    assert "[EMAIL]" in out
    assert "petrov" not in out.lower()


def test_redact_keeps_merchant_text_and_amounts():
    for raw in ("LENTA 5", "МАГНИТ 123", "PYATEROCHKA SUPERMARKET", "ОПЛАТА 1 234,56"):
        assert redact(raw) == raw


def test_user_prompt_masks_pii(monkeypatch):
    monkeypatch.delenv("SPENDTRACK_LLM_REDACT", raising=False)
    tx = {"description": "ПЕРЕВОД НА КАРТУ 4276 1234 5678 9010", "merchant": "",
          "amount_kopecks": -150000}
    text = prompts.build_user_prompt(tx)
    assert "[CARD]" in text
    assert "4276" not in text
    assert "amount: -1500.00" in text  # сумма остаётся: без неё классификация невозможна


def test_user_prompt_opt_out(monkeypatch):
    monkeypatch.setenv("SPENDTRACK_LLM_REDACT", "0")
    tx = {"description": "КАРТА 4276 1234 5678 9010", "merchant": "",
          "amount_kopecks": -100}
    assert "4276" in prompts.build_user_prompt(tx)


def test_redact_iban_and_account():
    for raw in ("BY12 ALFA 3012 3456 7890 1234", "BY12ALFA3012345678901234"):
        out = redact(raw)
        assert "[IBAN]" in out
        assert "3012" not in out


def test_redact_belarus_phone():
    out = redact("+375 29 123-45-67")
    assert "[PHONE]" in out
    assert "123-45-67" not in out


def test_redact_false_positives():
    for raw in ("12.09.2026", "ОПЛАТА 1 234,56", "ЗАКАЗ 12345", "LENTA 5"):
        assert redact(raw) == raw


def test_redact_idempotent():
    once = redact("КАРТА 4276 1234 5678 9010, +7 999 123-45-67, a@b.co")
    assert redact(once) == once


def test_few_shot_examples_are_redacted(monkeypatch):
    monkeypatch.delenv("SPENDTRACK_LLM_REDACT", raising=False)
    examples = [{"description": "ОПЛАТА 4276 1234 5678 9010", "amount_kopecks": -100,
                 "category": "groceries"}]
    taxonomy = load_taxonomy()
    system = prompts.build_system_prompt(examples, taxonomy)
    assert "4276" not in system
    assert "[CARD]" in system
