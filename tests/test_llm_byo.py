"""BYO-LLM/Ollama: явный выбор провайдера, отсутствие тихих фолбэков, офлайн по умолчанию."""
from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock, patch

import pytest

from spendtrack import llm as llm_mod
from spendtrack.config import LLMEndpoint, LLMSettings, Settings
from spendtrack.llm import LLMProvider, call_llm, llm_status, resolve_providers

OK_JSON = '{"category":"groceries","confidence":0.95,"merchant":"X","reason":"r"}'


@pytest.fixture(autouse=True)
def _clean_breakers():
    """Breakers — модульное состояние: изолируем тесты друг от друга."""
    llm_mod._breakers.clear()
    yield
    llm_mod._breakers.clear()


def _settings(**overrides) -> Settings:
    """Герметичные настройки: env/`.env` не влияют (все поля заданы явно)."""
    data: dict = {
        "llm": LLMSettings(
            primary=LLMEndpoint(base_url="https://openrouter.ai/api/v1", model="free-primary"),
            fallback=LLMEndpoint(base_url="http://localhost:3001/v1", model="free-fallback"),
            deepseek=LLMEndpoint(base_url="http://127.0.0.1:3201/v1", model="free-shim"),
            offline=LLMEndpoint(base_url="http://127.0.0.1:11434/v1", model="qwen2.5-coder:3b"),
        ),
        "freel_llm_api_key": "",
        "openrouter_api_key": "",
        "llm_provider": "",
        "llm_base_url": "",
        "llm_model": "",
        "llm_api_key": "",
    }
    data.update(overrides)
    return Settings(**data)


def test_off_by_default(monkeypatch):
    """Нет конфига — нет провайдеров: ноль сети, всё спорное уходит человеку."""
    monkeypatch.delenv("SPENDTRACK_ALLOW_LOCAL_LLM", raising=False)
    assert resolve_providers(_settings()) == ()
    assert llm_status(_settings())["mode"] == "off"


def test_byo_wins_over_free_chain(monkeypatch):
    """BYO-эндпоинт — единственный провайдер, даже если ключи free-каналов заданы."""
    monkeypatch.delenv("SPENDTRACK_ALLOW_LOCAL_LLM", raising=False)
    cfg = _settings(llm_base_url="https://llm.example/v1", llm_model="my-model",
                    llm_api_key="sk-byo", openrouter_api_key="sk-or", freel_llm_api_key="sk-fl")
    assert resolve_providers(cfg) == (
        LLMProvider("https://llm.example/v1", "my-model", "sk-byo", "byo", False),
    )


def test_byo_local_without_allow_flag(monkeypatch):
    """Явно указанный локальный BYO (LM Studio и т.п.) — без ALLOW_LOCAL_LLM."""
    monkeypatch.delenv("SPENDTRACK_ALLOW_LOCAL_LLM", raising=False)
    cfg = _settings(llm_base_url="http://127.0.0.1:1234/v1", llm_model="local-model")
    (p,) = resolve_providers(cfg)
    assert p.source == "byo" and p.local is True and p.api_key == "no-key"


def test_ollama_preset_without_allow_flag(monkeypatch):
    """Пресет ollama — локальный путь без ключа и без opt-in флага."""
    monkeypatch.delenv("SPENDTRACK_ALLOW_LOCAL_LLM", raising=False)
    cfg = _settings(llm_provider="ollama", llm_model="qwen2.5:3b")
    assert resolve_providers(cfg) == (
        LLMProvider("http://127.0.0.1:11434/v1", "qwen2.5:3b", "no-key", "ollama", True),
    )


def test_ollama_preset_default_model_from_settings(monkeypatch):
    """Модель по умолчанию для Ollama берётся из llm.offline (settings.toml)."""
    monkeypatch.delenv("SPENDTRACK_ALLOW_LOCAL_LLM", raising=False)
    (p,) = resolve_providers(_settings(llm_provider="ollama"))
    assert p.model == "qwen2.5-coder:3b"


def test_byo_local_without_model_uses_offline_model(caplog):
    """Локальный BYO без SPENDTRACK_LLM_MODEL → модель Ollama + предупреждение в лог."""
    cfg = _settings(llm_base_url="http://127.0.0.1:1234/v1")
    with caplog.at_level(logging.WARNING, logger="spendtrack"):
        (p,) = resolve_providers(cfg)
    assert p.model == "qwen2.5-coder:3b"
    assert any("SPENDTRACK_LLM_MODEL" in r.getMessage() for r in caplog.records)


def test_byo_remote_without_model_warns(caplog):
    """Удалённый BYO без модели — дефолт primary + предупреждение (модель надо указать явно)."""
    cfg = _settings(llm_base_url="https://llm.example/v1")
    with caplog.at_level(logging.WARNING, logger="spendtrack"):
        (p,) = resolve_providers(cfg)
    assert p.model == "free-primary"
    assert any("SPENDTRACK_LLM_MODEL" in r.getMessage() for r in caplog.records)



def test_unknown_provider_fails_closed(caplog, monkeypatch):
    """C4 (Astra 01.10): опечатка в SPENDTRACK_LLM_PROVIDER — отказ, а не тихий free-фолбэк."""
    monkeypatch.delenv("SPENDTRACK_ALLOW_LOCAL_LLM", raising=False)
    cfg = _settings(llm_provider="llmstudio", openrouter_api_key="sk-or")
    with caplog.at_level(logging.WARNING, logger="spendtrack"):
        providers = resolve_providers(cfg)
    assert providers == ()
    assert any("неизвестный" in r.getMessage() for r in caplog.records)


def test_ollama_preset_rejects_remote_base(monkeypatch):
    """C4: пресет ollama с удалённым base_url — отказ (для внешнего сервера нужен явный BYO)."""
    monkeypatch.delenv("SPENDTRACK_ALLOW_LOCAL_LLM", raising=False)
    cfg = _settings(llm_provider="ollama", llm_base_url="https://remote.example/v1")
    assert resolve_providers(cfg) == ()


def test_is_local_covers_loopback_range():
    """S14 (Astra 01.10): 127.0.0.0/8 — loopback (а не только 127.0.0.1)."""
    from spendtrack.llm import _is_local
    assert _is_local("http://127.0.0.2:3001/v1") is True
    assert _is_local("http://localhost:3001/v1") is True
    assert _is_local("http://10.0.0.1/v1") is False


def test_override_key_matches_url(monkeypatch):
    """endpoint_override с openrouter-URL получает OPENROUTER-ключ (внутренний шов)."""
    monkeypatch.delenv("SPENDTRACK_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("SPENDTRACK_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("SPENDTRACK_ALLOW_LOCAL_LLM", raising=False)
    monkeypatch.setenv("SPENDTRACK_OPENROUTER_API_KEY", "sk-or")
    captured: dict = {}

    def fake_openai(base_url, api_key="", timeout=..., max_retries=None):
        mock = MagicMock()

        def create(**kwargs):
            captured.update(base_url=base_url, api_key=api_key)
            resp = MagicMock()
            resp.choices[0].message.content = OK_JSON
            return resp

        mock.chat.completions.create = create
        return mock

    with patch.object(llm_mod, "OpenAI", fake_openai):
        res = call_llm("sys", "usr", max_tokens=10,
                       endpoint_override="https://openrouter.ai/api/v1")

    assert res["source"] == "override"
    assert captured["api_key"] == "sk-or"


def test_byo_failure_does_not_fall_back_to_free(monkeypatch):
    """BYO недоступен → failed/очередь, никакого тихого отката в free-каналы."""
    monkeypatch.setenv("SPENDTRACK_LLM_BASE_URL", "https://llm.example/v1")
    monkeypatch.setenv("SPENDTRACK_LLM_MODEL", "byo-model")
    monkeypatch.setenv("SPENDTRACK_LLM_API_KEY", "sk-byo")
    monkeypatch.setenv("SPENDTRACK_OPENROUTER_API_KEY", "sk-or")
    attempted: list[str] = []

    def fake_openai(base_url, api_key="", timeout=..., max_retries=None):
        mock = MagicMock()

        def create(**kwargs):
            attempted.append(base_url)
            raise RuntimeError(f"byo down: {base_url}")

        mock.chat.completions.create = create
        return mock

    with patch.object(llm_mod, "OpenAI", fake_openai):
        res = call_llm("sys", "usr", max_tokens=10)

    assert res == {"content": "", "model": "none", "source": "failed"}
    assert attempted == ["https://llm.example/v1"]


def test_byo_success_reports_source(monkeypatch):
    """Успешный BYO-вызов возвращает source=byo и контент модели."""
    monkeypatch.setenv("SPENDTRACK_LLM_BASE_URL", "https://llm.example/v1")
    monkeypatch.setenv("SPENDTRACK_LLM_MODEL", "byo-model")
    monkeypatch.setenv("SPENDTRACK_LLM_API_KEY", "sk-byo")

    def fake_openai(base_url, api_key="", timeout=..., max_retries=None):
        mock = MagicMock()
        resp = MagicMock()
        resp.choices[0].message.content = OK_JSON
        mock.chat.completions.create.return_value = resp
        return mock

    with patch.object(llm_mod, "OpenAI", fake_openai):
        res = call_llm("sys", "usr", max_tokens=10)

    assert res == {"content": OK_JSON, "model": "byo-model", "source": "byo"}


def test_client_disables_sdk_retries(monkeypatch):
    """S1 (ревью 28.09): SDK-ретраи выключены — за повторы отвечают цепочка провайдеров и брейкер."""
    monkeypatch.setenv("SPENDTRACK_LLM_BASE_URL", "https://llm.example/v1")
    monkeypatch.setenv("SPENDTRACK_LLM_MODEL", "byo-model")
    monkeypatch.setenv("SPENDTRACK_LLM_API_KEY", "sk-byo")
    captured: dict = {}

    def fake_openai(base_url, api_key="", timeout=..., max_retries=None):
        captured["max_retries"] = max_retries
        mock = MagicMock()
        resp = MagicMock()
        resp.choices[0].message.content = OK_JSON
        mock.chat.completions.create.return_value = resp
        return mock

    with patch.object(llm_mod, "OpenAI", fake_openai):
        call_llm("sys", "usr", max_tokens=10)

    assert captured["max_retries"] == 0


def test_provider_failure_is_logged(monkeypatch, caplog):
    """S2 (ревью 28.09): сбой провайдера виден в логе (тип ошибки, без тела ответа)."""
    monkeypatch.setenv("SPENDTRACK_LLM_BASE_URL", "https://llm.example/v1")
    monkeypatch.setenv("SPENDTRACK_LLM_MODEL", "byo-model")
    monkeypatch.setenv("SPENDTRACK_LLM_API_KEY", "sk-byo")

    def fake_openai(base_url, api_key="", timeout=..., max_retries=None):
        mock = MagicMock()
        mock.chat.completions.create.side_effect = RuntimeError("boom")
        return mock

    with (
        caplog.at_level(logging.WARNING, logger="spendtrack"),
        patch.object(llm_mod, "OpenAI", fake_openai),
    ):
        res = call_llm("sys", "usr", max_tokens=10)

    assert res["source"] == "failed"
    assert any("RuntimeError" in r.getMessage() for r in caplog.records)


def test_free_chain_key_matches_endpoint(monkeypatch):
    """Ключ подбирается под URL: openrouter-эндпоинт → OPENROUTER-ключ (фикс swap c90e43e)."""
    monkeypatch.delenv("SPENDTRACK_ALLOW_LOCAL_LLM", raising=False)
    cfg = _settings(openrouter_api_key="sk-or")
    (p,) = resolve_providers(cfg)
    assert p.source == "primary" and p.api_key == "sk-or"

    cfg2 = _settings(freel_llm_api_key="sk-fl")
    assert resolve_providers(cfg2) == ()  # локальный шим без opt-in не участвует

    monkeypatch.setenv("SPENDTRACK_ALLOW_LOCAL_LLM", "1")
    providers = resolve_providers(cfg2)
    assert [p.source for p in providers] == ["fallback", "deepseek"]
    assert providers[0].api_key == "sk-fl"


def test_llm_status_free_hides_key(monkeypatch):
    """free-режим перечисляет каналы, но никогда не показывает ключи."""
    monkeypatch.delenv("SPENDTRACK_ALLOW_LOCAL_LLM", raising=False)
    cfg = _settings(openrouter_api_key="sk-or-secret")
    status = llm_status(cfg)
    assert status["mode"] == "free"
    assert status["providers"][0]["has_key"] is True
    assert "sk-or-secret" not in json.dumps(status, ensure_ascii=False)
    assert all("api_key" not in p for p in status["providers"])


def test_cli_llm_status_json(monkeypatch, capsys):
    """CLI `llm-status --json` не ходит в сеть и отдаёт валидный режим."""
    from spendtrack.cli import main

    monkeypatch.delenv("SPENDTRACK_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("SPENDTRACK_LLM_PROVIDER", raising=False)
    assert main(["llm-status", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["mode"] in ("off", "byo", "ollama", "free")


def test_parse_llm_json_array_is_none():
    """S9 (Astra 01.10): валидный JSON-массив не «выковыривается» regex-фолбэком."""
    assert llm_mod.parse_llm_json('[{"category":"groceries","confidence":0.99}]') is None
    assert llm_mod.parse_llm_json(OK_JSON)["category"] == "groceries"


def test_llm_status_hides_url_secrets(monkeypatch):
    """S15 (Astra 01.10): base_url с userinfo/query не утекает в статус."""
    monkeypatch.delenv("SPENDTRACK_ALLOW_LOCAL_LLM", raising=False)
    cfg = _settings(llm_base_url="https://user:secret@llm.example/v1?token=secret",
                    llm_model="m", llm_api_key="sk-byo")
    text = json.dumps(llm_status(cfg), ensure_ascii=False)
    assert "secret" not in text
    assert "llm.example" in text


def test_empty_response_is_failure_and_falls_back(monkeypatch):
    """S10 (Astra 01.10): HTTP-200 с пустым content — сбой: пробуем следующий провайдер."""
    monkeypatch.setattr(llm_mod, "resolve_providers", lambda cfg=None: (
        LLMProvider("https://first.example/v1", "m1", "k1", "byo", False),
        LLMProvider("https://second.example/v1", "m2", "k2", "byo", False),
    ))
    calls: list[str] = []

    def fake_openai(base_url, api_key="", timeout=..., max_retries=None):
        mock = MagicMock()

        def create(**kwargs):
            calls.append(base_url)
            resp = MagicMock()
            resp.choices[0].message.content = "" if base_url.startswith("https://first") else OK_JSON
            return resp

        mock.chat.completions.create = create
        return mock

    with patch.object(llm_mod, "OpenAI", fake_openai):
        res = call_llm("sys", "usr", max_tokens=10)

    assert calls == ["https://first.example/v1", "https://second.example/v1"]
    assert res["content"] == OK_JSON


def test_env_key_requires_exact_openrouter_origin():
    """S13 (Astra 01.10): OpenRouter-ключ — только точному origin, не подстроке URL."""
    from spendtrack.llm import _env_key_for

    cfg = _settings(openrouter_api_key="sk-or", freel_llm_api_key="sk-fl")
    assert _env_key_for("https://openrouter.ai/api/v1", cfg) == "sk-or"
    assert _env_key_for("https://collector.example/v1?openrouter", cfg) == "sk-fl"
    assert _env_key_for("https://openrouter.ai.evil.example/v1", cfg) == "sk-fl"


def test_client_closed_after_call(monkeypatch):
    """S12 (Astra 01.10): HTTP-клиент закрывается после вызова (не зависит от GC)."""
    monkeypatch.setenv("SPENDTRACK_LLM_BASE_URL", "https://llm.example/v1")
    monkeypatch.setenv("SPENDTRACK_LLM_MODEL", "byo-model")
    monkeypatch.setenv("SPENDTRACK_LLM_API_KEY", "sk-byo")
    closed: list[bool] = []

    def fake_openai(base_url, api_key="", timeout=..., max_retries=None):
        mock = MagicMock()
        resp = MagicMock()
        resp.choices[0].message.content = OK_JSON
        mock.chat.completions.create.return_value = resp
        mock.close.side_effect = lambda: closed.append(True)
        return mock

    with patch.object(llm_mod, "OpenAI", fake_openai):
        call_llm("sys", "usr", max_tokens=10)

    assert closed == [True]
