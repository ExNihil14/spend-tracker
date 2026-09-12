from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from spendtrack.config import load_settings


def get_client(endpoint: str | None = None) -> tuple[OpenAI, str, str]:
    cfg = load_settings()
    base = endpoint or cfg.llm.primary.base_url
    key = cfg.freel_llm_api_key or "no-key"
    if "openrouter" in base:
        key = cfg.openrouter_api_key or "no-key"
    return OpenAI(base_url=base, api_key=key), base, cfg.llm.primary.model


def call_llm(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 400,
    temperature: float = 0.1,
    endpoint_override: str | None = None,
    model_override: str | None = None,
) -> dict[str, Any]:
    """Вызов LLM с фолбэком. Возвращает {'content': str, 'model': str, 'source': str}."""
    cfg = load_settings()

    attempts = [
        (cfg.llm.primary.base_url, cfg.llm.primary.model, cfg.freel_llm_api_key or "no-key", "primary"),
        (cfg.llm.fallback.base_url, cfg.llm.fallback.model, cfg.openrouter_api_key or "no-key", "fallback"),
    ]
    if endpoint_override:
        attempts = [(endpoint_override, model_override or cfg.llm.primary.model,
                      cfg.freel_llm_api_key or "no-key", "override")] + attempts

    for base_url, model, api_key, source in attempts:
        try:
            client = OpenAI(base_url=base_url, api_key=api_key)
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            content = resp.choices[0].message.content or ""
            return {"content": content, "model": model, "source": source}
        except Exception:  # noqa: BLE001, S112
            continue

    return {"content": "", "model": "none", "source": "failed"}


def parse_llm_json(raw: str) -> dict | None:
    """Парсит JSON из ответа LLM; возвращает dict или None."""
    if not raw.strip():
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    import re
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return None