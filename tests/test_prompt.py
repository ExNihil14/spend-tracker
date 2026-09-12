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


def test_parse_json_clean():
    assert parse_llm_json('{"category":"groceries","confidence":0.9}')["category"] == "groceries"


def test_parse_json_with_code_fence():
    assert parse_llm_json('```json\n{"category":"fuel","confidence":0.95}\n```')["category"] == "fuel"


def test_parse_json_inline():
    assert parse_llm_json('Результат: {"category":"transport","confidence":0.7} конец')["category"] == "transport"


def test_parse_json_garbage():
    assert parse_llm_json("никак не жсон") is None