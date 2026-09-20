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


def test_unknown_provider_warns_and_uses_free_chain(caplog, monkeypatch):
    """Опечатка в SPENDTRACK_LLM_PROVIDER не ломает резолв, но видна в логе."""
    monkeypatch.delenv("SPENDTRACK_ALLOW_LOCAL_LLM", raising=False)
    cfg = _settings(llm_provider="llmstudio", openrouter_api_key="sk-or")
    with caplog.at_level(logging.WARNING, logger="spendtrack"):
        providers = resolve_providers(cfg)
    assert [p.source for p in providers] == ["primary"]
    assert any("неизвестный" in r.getMessage() for r in caplog.records)


def test_override_key_matches_url(monkeypatch):
    """endpoint_override с openrouter-URL получает OPENROUTER-ключ (внутренний шов)."""
    monkeypatch.delenv("SPENDTRACK_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("SPENDTRACK_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("SPENDTRACK_ALLOW_LOCAL_LLM", raising=False)
    monkeypatch.setenv("SPENDTRACK_OPENROUTER_API_KEY", "sk-or")
    captured: dict = {}

    def fake_openai(base_url, api_key="", timeout=...):
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

    def fake_openai(base_url, api_key="", timeout=...):
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

    def fake_openai(base_url, api_key="", timeout=...):
        mock = MagicMock()
        resp = MagicMock()
        resp.choices[0].message.content = OK_JSON
        mock.chat.completions.create.return_value = resp
        return mock

    with patch.object(llm_mod, "OpenAI", fake_openai):
        res = call_llm("sys", "usr", max_tokens=10)

    assert res == {"content": OK_JSON, "model": "byo-model", "source": "byo"}


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
