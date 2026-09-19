from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any
from urllib.parse import urlparse

import httpx
from openai import OpenAI

from spendtrack.config import load_settings
from spendtrack.resilience import CircuitBreaker

log = logging.getLogger("spendtrack")

REQUEST_TIMEOUT_S = httpx.Timeout(30.0, connect=3.0)  # read=30 (батч), connect=3 (мёртвый порт)

_breakers: dict[str, CircuitBreaker] = {}
_br_lock = threading.Lock()


def _breaker(source: str) -> CircuitBreaker:
    with _br_lock:
        if source not in _breakers:
            _breakers[source] = CircuitBreaker(source, fail_threshold=3, recovery_s=1800.0)
        return _breakers[source]


def get_client(endpoint: str | None = None) -> tuple[OpenAI, str, str]:
    cfg = load_settings()
    base = endpoint or cfg.llm.primary.base_url
    key = cfg.freel_llm_api_key or "no-key"
    if "openrouter" in base:
        key = cfg.openrouter_api_key or "no-key"
    return OpenAI(base_url=base, api_key=key, timeout=REQUEST_TIMEOUT_S), base, cfg.llm.primary.model


def _is_local(url: str) -> bool:
    return (urlparse(url).hostname or "").lower() in {"127.0.0.1", "localhost", "::1"}


def _allow_local_llm() -> bool:
    """Локальные эндпоинты (shim) — только явный opt-in: они тоже проксируют наружу."""
    return os.environ.get("SPENDTRACK_ALLOW_LOCAL_LLM", "").strip().lower() in ("1", "true", "yes")


def call_llm(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 400,
    temperature: float = 0.1,
    endpoint_override: str | None = None,
    model_override: str | None = None,
) -> dict[str, Any]:
    """Вызов LLM с фолбэком. Возвращает {'content': str, 'model': str, 'source': str}.

    Offline-first: провайдер участвует только если для него есть ключ (или это локальный
    эндпоинт с явным SPENDTRACK_ALLOW_LOCAL_LLM=1). Без ключей сеть не трогается вообще —
    неизвестные операции уходят в очередь подтверждения, данные никуда не отправляются.
    """
    cfg = load_settings()

    candidates = [
        (cfg.llm.primary.base_url, cfg.llm.primary.model, cfg.freel_llm_api_key, "primary"),
        (cfg.llm.fallback.base_url, cfg.llm.fallback.model, cfg.openrouter_api_key, "fallback"),
        (cfg.llm.deepseek.base_url, cfg.llm.deepseek.model, "", "deepseek"),
    ]
    if endpoint_override:
        candidates.insert(0, (endpoint_override, model_override or cfg.llm.primary.model,
                              cfg.freel_llm_api_key, "override"))
    attempts = [
        (base_url, model, key or "no-key", source)
        for base_url, model, key, source in candidates
        if key or (_is_local(base_url) and _allow_local_llm())
    ]
    if not attempts:
        log.info("llm: провайдеры не настроены — офлайн-режим (сеть не трогаем)")
        return {"content": "", "model": "none", "source": "offline"}

    for base_url, model, api_key, source in attempts:
        br = _breaker(source)
        if not br.allowed():
            log.info("llm[%s]: circuit open — пропуск без вызова", source)
            continue
        try:
            client = OpenAI(base_url=base_url, api_key=api_key, timeout=REQUEST_TIMEOUT_S)
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
            br.report_success()
            return {"content": content, "model": model, "source": source}
        except Exception:  # noqa: BLE001
            br.report_failure()
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