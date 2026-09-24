from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
from openai import OpenAI

from spendtrack.config import Settings, load_settings
from spendtrack.resilience import CircuitBreaker

log = logging.getLogger("spendtrack")

REQUEST_TIMEOUT_S = httpx.Timeout(30.0, connect=3.0)  # read=30 (батч), connect=3 (мёртвый порт)

_breakers: dict[str, CircuitBreaker] = {}
_br_lock = threading.Lock()


@dataclass(frozen=True)
class LLMProvider:
    """Неизменяемое описание провайдера: куда идти, что запрашивать и с каким ключом."""

    base_url: str
    model: str
    api_key: str
    source: str  # byo | ollama | primary | fallback | deepseek | override
    local: bool = False


def _breaker(source: str) -> CircuitBreaker:
    with _br_lock:
        if source not in _breakers:
            _breakers[source] = CircuitBreaker(source, fail_threshold=3, recovery_s=1800.0)
        return _breakers[source]


def _env_key_for(base_url: str, cfg: Settings) -> str:
    """Ключ подбирается под эндпоинт (openrouter-URL → OPENROUTER key, иначе FreeLLM-ключ)."""
    if "openrouter" in base_url:
        return cfg.openrouter_api_key
    return cfg.freel_llm_api_key


def _is_local(url: str) -> bool:
    return (urlparse(url).hostname or "").lower() in {"127.0.0.1", "localhost", "::1"}


def _allow_local_llm() -> bool:
    """Локальные эндпоинты (shim) — только явный opt-in: они тоже проксируют наружу."""
    return os.environ.get("SPENDTRACK_ALLOW_LOCAL_LLM", "").strip().lower() in ("1", "true", "yes")


def resolve_providers(cfg: Settings | None = None) -> tuple[LLMProvider, ...]:
    """Чистый резолв провайдеров без сети (тестируемый): BYO/Ollama → free-цепочка → ().

    Приоритет: BYO-эндпоинт пользователя (SPENDTRACK_LLM_BASE_URL или пресет ollama)
    полностью вытесняет free-цепочку — данные уходят ровно туда, куда указал пользователь,
    без «тихих» фолбэков в чужое облако. Пустой результат = офлайн-режим.
    """
    cfg = cfg or load_settings()
    provider = (cfg.llm_provider or "").strip().lower()
    base = (cfg.llm_base_url or "").strip()
    model = (cfg.llm_model or "").strip()
    key = (cfg.llm_api_key or "").strip()

    if provider == "ollama" and not base:  # локальный пресет: полностью на своей машине
        base, model = cfg.llm.offline.base_url, model or cfg.llm.offline.model
        return (LLMProvider(base, model, key or "no-key", "ollama", True),)

    if provider and provider != "ollama" and not base:
        log.warning("llm: неизвестный SPENDTRACK_LLM_PROVIDER=%r — игнорирую (ожидается 'ollama' "
                    "или SPENDTRACK_LLM_BASE_URL для BYO)", provider)

    if base:  # BYO: явное согласие пользователя, ALLOW_LOCAL_LLM не требуется
        local = _is_local(base)
        if not model:  # без явной модели берём осмысленный дефолт и предупреждаем
            model = cfg.llm.offline.model if local else cfg.llm.primary.model
            log.warning("llm: SPENDTRACK_LLM_MODEL не задан — использую %r (укажите модель вашего сервера)",
                        model)
        return (LLMProvider(base, model, key or "no-key", "byo", local),)

    chain = (
        (cfg.llm.primary.base_url, cfg.llm.primary.model,
         _env_key_for(cfg.llm.primary.base_url, cfg), "primary"),
        (cfg.llm.fallback.base_url, cfg.llm.fallback.model,
         _env_key_for(cfg.llm.fallback.base_url, cfg), "fallback"),
        (cfg.llm.deepseek.base_url, cfg.llm.deepseek.model, "", "deepseek"),
    )
    providers = []
    for base_url, model_name, api_key, source in chain:
        local = _is_local(base_url)
        if local:  # шимы-прокси наружу — только явный opt-in (ключ сам по себе не согласие)
            if _allow_local_llm():
                # "no-key": локальные шимы (3001/3201) авторизацию не проверяют, а openai-SDK
                # требует непустой api_key; так работало и до BYO (deepseek-шим без ключа).
                providers.append(LLMProvider(base_url, model_name, api_key or "no-key", source, True))
        elif api_key:
            providers.append(LLMProvider(base_url, model_name, api_key, source, False))
    return tuple(providers)


def llm_status(cfg: Settings | None = None) -> dict[str, Any]:
    """Текущий режим LLM без сети и без секретов (для CLI/диагностики).

    Возвращает новый dict на каждый вызов; внутреннее состояние модуля не шарится (значение-снимок).
    """
    cfg = cfg or load_settings()
    providers = resolve_providers(cfg)
    if not providers:
        return {"mode": "off", "providers": [],
                "note": "LLM выключен: данные не покидают машину, спорные строки — в очередь"}
    first = providers[0]
    mode = first.source if first.source in ("byo", "ollama") else "free"
    return {
        "mode": mode,
        "providers": [
            {"source": p.source, "base_url": p.base_url, "model": p.model,
             "local": p.local, "has_key": p.api_key != "no-key"}
            for p in providers
        ],
    }


def call_llm(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 400,
    temperature: float = 0.1,
    endpoint_override: str | None = None,
    model_override: str | None = None,
) -> dict[str, Any]:
    """Вызов LLM. Возвращает {'content': str, 'model': str, 'source': str}.

    Offline-first: провайдер участвует только если он задан явно — BYO (SPENDTRACK_LLM_BASE_URL /
    пресет ollama — свой ключ/сервер пользователя) или free-канал с ключом (локальные шимы — с
    SPENDTRACK_ALLOW_LOCAL_LLM=1). Без этого сеть не трогается вообще — неизвестные операции
    уходят в очередь подтверждения. BYO вытесняет free-цепочку и в неё не откатывается.

    `endpoint_override` — внутренний механизм (тесты/диагностика): ключ подбирается по URL, локальный
    хост требует ALLOW_LOCAL_LLM=1 (в отличие от BYO-конфига пользователя, где согласие уже явное).
    """
    cfg = load_settings()
    providers = list(resolve_providers(cfg))

    if endpoint_override:
        key = _env_key_for(endpoint_override, cfg)
        local = _is_local(endpoint_override)
        if (local and _allow_local_llm()) or (not local and key):
            providers.insert(0, LLMProvider(
                endpoint_override, model_override or cfg.llm.primary.model,
                key or "no-key", "override", local,
            ))
    if not providers:
        log.info("llm: провайдеры не настроены — офлайн-режим (сеть не трогаем)")
        return {"content": "", "model": "none", "source": "offline"}

    for provider in providers:
        br = _breaker(provider.source)
        if not br.allowed():
            log.info("llm[%s]: circuit open — пропуск без вызова", provider.source)
            continue
        try:
            client = OpenAI(base_url=provider.base_url, api_key=provider.api_key,
                            timeout=REQUEST_TIMEOUT_S)
            resp = client.chat.completions.create(
                model=provider.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            content = resp.choices[0].message.content or ""
            br.report_success()
            return {"content": content, "model": provider.model, "source": provider.source}
        except Exception:  # noqa: BLE001
            br.report_failure()
            continue

    return {"content": "", "model": "none", "source": "failed"}


def parse_llm_json(raw: str) -> dict | None:
    """Парсит JSON из ответа LLM; возвращает dict или None."""
    if not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):  # аудит 24.09: list/str/int от LLM не должны ронять партию
            return parsed
    except json.JSONDecodeError:
        pass
    import re
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            parsed = json.loads(m.group())
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return None