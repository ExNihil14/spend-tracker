"""Egress-redaction: PII не уходит в LLM (privacy pack 21.10).

Контракт:
* маскируются карточные/счётные номера, телефоны, e-mail в `description`/`merchant` и в few-shot;
* обычный текст и короткие числа (суммы, «LENTA 5») не трогаются — иначе категоризация деградирует;
* выключение — `SPENDTRACK_LLM_REDACT=0` (осознанный opt-out, напр. полностью локальный Ollama;
  для удалённых провайдеров `call_llm` всё равно чистит payload);
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


def test_user_prompt_masks_account_and_phone_without_prefix(monkeypatch):
    monkeypatch.delenv("SPENDTRACK_LLM_REDACT", raising=False)
    tx = {"description": "ПЕРЕВОД 40817810099910004312, тел. 79161234567",
          "merchant": "", "amount_kopecks": -100}
    text = prompts.build_user_prompt(tx)
    assert "[CARD]" in text and "[PHONE]" in text
    assert "40817" not in text and "916" not in text


def test_user_prompt_opt_out(monkeypatch):
    monkeypatch.setenv("SPENDTRACK_LLM_REDACT", "0")
    tx = {"description": "КАРТА 4276 1234 5678 9010", "merchant": "",
          "amount_kopecks": -100}
    assert "4276" in prompts.build_user_prompt(tx)


def test_remote_llm_forces_redaction_even_with_opt_out(monkeypatch):
    """Opt-out разрешён только для локального провайдера: удалённый канал всегда чистит payload."""
    from unittest.mock import MagicMock, patch

    from spendtrack import llm as llm_mod
    from spendtrack.llm import LLMProvider

    monkeypatch.setenv("SPENDTRACK_LLM_REDACT", "0")
    captured: dict = {}
    resp = MagicMock()
    resp.choices[0].message.content = '{"category":"other","confidence":0.0}'

    def fake_openai(base_url, api_key="", timeout=20.0, max_retries=None):
        mock = MagicMock()

        def create(**kwargs):
            captured.update(kwargs)
            return resp

        mock.chat.completions.create = create
        return mock

    monkeypatch.setattr(
        llm_mod, "resolve_providers",
        lambda cfg=None: (LLMProvider("https://remote.example/v1", "m", "k", "test", False),),
    )
    with patch.object(llm_mod, "OpenAI", fake_openai):
        llm_mod.call_llm("system 4276 1234 5678 9010", "user +7 916 123-45-67", max_tokens=10)

    messages = captured["messages"]
    payload = "\n".join(m["content"] for m in messages)
    assert "4276" not in payload and "[CARD]" in payload
    assert "916" not in payload and "[PHONE]" in payload


def test_loopback_shim_forces_redaction_with_opt_out(monkeypatch):
    """P1 25.10: loopback shim может egress; opt-out не должен снимать redaction."""
    from unittest.mock import MagicMock, patch

    from spendtrack import llm as llm_mod
    from spendtrack.llm import LLMProvider

    monkeypatch.setenv("SPENDTRACK_LLM_REDACT", "0")
    captured = {}
    resp = MagicMock()
    resp.choices[0].message.content = '{"category":"other","confidence":0.0}'

    def fake_openai(base_url, api_key="", timeout=20.0, max_retries=None):
        mock = MagicMock()
        mock.chat.completions.create = lambda **kw: captured.update(kw) or resp
        return mock

    monkeypatch.setattr(
        llm_mod, "resolve_providers",
        lambda cfg=None: (LLMProvider("http://127.0.0.1:3201/v1", "m", "no-key",
                                      "primary", True),),
    )
    with patch.object(llm_mod, "OpenAI", fake_openai):
        llm_mod.call_llm("system 4276 1234 5678 9010", "user +7 916 123-45-67", max_tokens=10)
    payload = "\n".join(m["content"] for m in captured["messages"])
    assert "4276" not in payload and "[CARD]" in payload
    assert "916" not in payload and "[PHONE]" in payload


def test_direct_ollama_opt_out_keeps_raw(monkeypatch):
    """Opt-out сохраняется только для прямого Ollama (no egress)."""
    from unittest.mock import MagicMock, patch

    from spendtrack import llm as llm_mod
    from spendtrack.llm import LLMProvider

    monkeypatch.setenv("SPENDTRACK_LLM_REDACT", "0")
    captured = {}
    resp = MagicMock()
    resp.choices[0].message.content = '{"category":"other","confidence":0.0}'

    def fake_openai(base_url, api_key="", timeout=20.0, max_retries=None):
        mock = MagicMock()
        mock.chat.completions.create = lambda **kw: captured.update(kw) or resp
        return mock

    monkeypatch.setattr(
        llm_mod, "resolve_providers",
        lambda cfg=None: (LLMProvider("http://127.0.0.1:11434/v1", "m", "no-key",
                                      "ollama", True),),
    )
    with patch.object(llm_mod, "OpenAI", fake_openai):
        llm_mod.call_llm("system 4276 1234 5678 9010", "user +7 916 123-45-67", max_tokens=10)
    payload = "\n".join(m["content"] for m in captured["messages"])
    assert "4276" in payload and "916" in payload


def test_redact_iban_and_account():
    for raw in ("BY12 ALFA 3012 3456 7890 1234", "BY12ALFA3012345678901234"):
        out = redact(raw)
        assert "[IBAN]" in out
        assert "3012" not in out


def test_redact_belarus_phone():
    out = redact("+375 29 123-45-67")
    assert "[PHONE]" in out
    assert "123-45-67" not in out


def test_redact_russian_account_20_digits():
    """РФ-счёт = 20 цифр; бывает слитно, с пробелами и NBSP (Abacus 23.10, P0)."""
    for raw in (
        "40817810099910004312",
        "40817 810 0 9991 0004312",
        "4081-7810-0999-1000-4312",
        "40817\u00a0810\u00a00\u00a09991\u00a00004312",
    ):
        out = redact(raw)
        assert "[CARD]" in out
        assert "40817" not in out and "04312" not in out


def test_redact_phone_without_plus_or_eight():
    """7916…/916… без +/8 — реальный формат выписок; не должен проходить (P0)."""
    for raw in (
        "79161234567",
        "9161234567",
        "7 916 123-45-67",
        "9 161 234-56-78",
        "8\u00a0916\u00a0123\u00a045\u00a067",
        "+7 (916) 123-45-67",
    ):
        out = redact(raw)
        assert "[PHONE]" in out
        assert "916" not in out


def test_redact_unicode_separators():
    """NBSP/узкий NBSP в картах и IBAN — тот же egress, что и обычный пробел."""
    card = redact("4276\u00a01234\u20075678\u202f9010")
    assert card == "[CARD]"
    for raw in (
        "BY12\u00a0ALFA\u00a03012\u00a03456\u00a07890\u00a01234",
        "by12 alfa 3012 3456 7890 1234",
    ):
        assert redact(raw) == "[IBAN]"


def test_redact_card_separators_and_grouping():
    """v1.1: U+2011/точки и 6-6-4 не должны ломаться phone-правилом."""
    for raw in (
        "4111\u20111111\u20111111\u20111111",
        "4111.1111.1111.1111",
        "411111 916123 4568",
    ):
        out = redact(raw)
        assert out == "[CARD]", (raw, out)
        assert "[PHONE]" not in out


def test_redact_dotted_account():
    raw = "р/с 40817.810.0.1234.5678901"
    out = redact(raw)
    assert "[CARD]" in out and "40817" not in out, out


def test_redact_iban_country_lengths_and_merchant_suffix():
    for raw in (
        "GB82 WEST 1234 5698 7654 32",
        "NL91  ABNA 0417 1643 00",
        "BE68 5390 0754 7034 UBER EATS",
        "FR14 2004 1010 0505 0001 3M02 606",
    ):
        out = redact(raw)
        assert "[IBAN]" in out, (raw, out)
    out = redact("BE68 5390 0754 7034 UBER EATS")
    assert out == "[IBAN] UBER EATS", out


def test_redact_contact_formats_v11():
    for raw in (
        "+44 20 7946 0958",
        "495 123-45-67",
        "8 (916) 123.45.67",
    ):
        out = redact(raw)
        assert "[PHONE]" in out, (raw, out)
    out = redact("pay@пример.рф")
    assert "[EMAIL]" in out, out


def test_redact_false_positives():
    for raw in (
        "12.09.2026",
        "ОПЛАТА 1 234,56",
        "ЗАКАЗ 12345",
        "LENTA 5",
        "LENTA 2026-09-12 12 345,67",
        "SHOP 2026-09-12 123456789012",
    ):
        assert redact(raw) == raw, (raw, redact(raw))


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


def test_merchant_pii_redacted_before_truncate():
    """P2 25.10: PII на границе merchant-лимита не разрезается."""
    tx = {"description": "X", "merchant": "M" * 75 + "4276123456789010",
          "amount_kopecks": -100}
    text = prompts._build_user_prompt(tx, allow_raw=False)
    assert "4276" not in text
    assert "9010" not in text


def test_unknown_dynamic_fields_not_sent(monkeypatch):
    """P2 25.10: только allowlist полей tx, даже при opt-out; лишние поля не уходят."""
    monkeypatch.setenv("SPENDTRACK_LLM_REDACT", "0")
    tx = {
        "description": "LENTA", "merchant": "LENTA", "amount_kopecks": -100,
        "note": "4276 1234 5678 9010", "raw_payload": "secret",
    }
    text = prompts.build_user_prompt(tx)
    assert "4276" not in text and "raw_payload" not in text and "secret" not in text


def test_few_shot_merchant_pii_redacted_before_truncate():
    """P2 25.10: few-shot description/merchant режутся только после redact."""
    examples = [{
        "description": "A" * 295 + "4276123456789010",
        "merchant": "M" * 75 + "4276123456789010",
        "amount_kopecks": -100,
        "category": "groceries",
    }]
    system = prompts._build_system_prompt(examples, load_taxonomy(), allow_raw=False)
    assert "4276" not in system
    assert "9010" not in system
