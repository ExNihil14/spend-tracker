from __future__ import annotations

from spendtrack.llm import parse_llm_json
from spendtrack.prompts import build_system_prompt, build_user_prompt
from spendtrack.store import parse_amount


def test_system_prompt_contains_taxonomy():
    prompt = build_system_prompt([])
    assert "groceries" in prompt
    assert "fuel" in prompt


def test_system_prompt_embeds_examples():
    prompt = build_system_prompt([
        {"description": "NETFLIX.COM", "amount_kopecks": parse_amount("-1549"), "category": "subscriptions"}
    ])
    assert "NETFLIX.COM" in prompt
    assert "subscriptions" in prompt


def test_user_prompt_contains_tx():
    prompt = build_user_prompt({
        "description": "ЛЕНТА", "amount_kopecks": parse_amount("-23.45"),
        "account_anon": "acc_1", "date": "2026-09-12",
    })
    assert "ЛЕНТА" in prompt
    assert "-23.45" in prompt


def test_user_prompt_truncates_long_description():
    long_desc = "X" * 400
    prompt = build_user_prompt({
        "description": long_desc, "amount_kopecks": parse_amount("-1"),
        "account_anon": None, "date": "2026-09-12",
    })
    assert "X" * 300 in prompt
    assert "X" * 301 not in prompt
    assert "…" in prompt


def test_user_prompt_keeps_short_description():
    prompt = build_user_prompt({
        "description": "ЛЕНТА", "amount_kopecks": parse_amount("-1"),
        "account_anon": None, "date": "2026-09-12",
    })
    assert "ЛЕНТА" in prompt
    assert "…" not in prompt


def test_system_prompt_truncates_long_example():
    prompt = build_system_prompt([
        {"description": "Y" * 400, "amount_kopecks": parse_amount("-100"), "category": "other"}
    ])
    assert "Y" * 300 in prompt
    assert "Y" * 301 not in prompt


def test_parse_json_clean():
    assert parse_llm_json('{"category":"groceries","confidence":0.9}')["category"] == "groceries"


def test_parse_json_with_code_fence():
    assert parse_llm_json('```json\n{"category":"fuel","confidence":0.95}\n```')["category"] == "fuel"


def test_parse_json_inline():
    assert parse_llm_json('Результат: {"category":"transport","confidence":0.7} конец')["category"] == "transport"


def test_parse_json_garbage():
    assert parse_llm_json("никак не жсон") is None

def test_few_shot_examples_single_braces():
    """Аудит 24.09: примеры в промпте — одиночные скобки (модель видела {{...}} и путала формат)."""
    from spendtrack.prompts import build_system_prompt

    text = build_system_prompt([{"description": "ЛЕНТА", "amount_kopecks": -2345,
                                 "category": "groceries"}])
    assert '{{"category"' not in text
    assert '"category":"groceries"' in text
