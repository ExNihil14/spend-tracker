from __future__ import annotations

from unittest.mock import MagicMock, patch

from spendtrack import llm as llm_mod
from spendtrack.config import load_settings
from spendtrack.llm import call_llm

OK_JSON = '{"category":"groceries","confidence":0.95,"merchant":"X","reason":"r"}'


def test_deepseek_endpoint_configured():
    cfg = load_settings()
    assert "3201" in cfg.llm.deepseek.base_url
    assert "deepseek" in cfg.llm.deepseek.model.lower()


def test_fallback_order_primary_fallback_deepseek(monkeypatch):
    """Порядок фолбэков: primary → fallback → deepseek (source=deepseek)."""
    cfg = load_settings()
    call_order: list[str] = []

    def fake_openai(base_url, api_key="", timeout=20.0):
        mock = MagicMock()

        def create(**kwargs):
            call_order.append(base_url)
            if base_url == cfg.llm.deepseek.base_url:
                resp = MagicMock()
                resp.choices[0].message.content = OK_JSON
                return resp
            raise RuntimeError(f"mock fail {base_url}")

        mock.chat.completions.create = create
        return mock

    with patch.object(llm_mod, "OpenAI", fake_openai):
        res = call_llm("sys", "usr", max_tokens=50)

    assert res["source"] == "deepseek"
    assert call_order == [
        cfg.llm.primary.base_url,
        cfg.llm.fallback.base_url,
        cfg.llm.deepseek.base_url,
    ]


def test_circuit_breaker_skips_dead_primary(monkeypatch):
    """3 фейла primary → breaker открыт → primary пропускается без вызова."""
    cfg = load_settings()
    llm_mod._breakers.clear()
    called: list[str] = []

    def fake_openai(base_url, api_key="", timeout=...):
        mock = MagicMock()

        def create(**kwargs):
            called.append(base_url)
            if base_url == cfg.llm.primary.base_url:
                raise RuntimeError(f"mock fail {base_url}")
            resp = MagicMock()
            resp.choices[0].message.content = OK_JSON
            return resp

        mock.chat.completions.create = create
        return mock

    with patch.object(llm_mod, "OpenAI", fake_openai):
        # 3 вызова: primary падает 3 раза → breaker primary открыт
        for _ in range(3):
            res = call_llm("sys", "usr", max_tokens=50)
            assert res["source"] == "fallback" or res["source"] == "deepseek"
        assert called.count(cfg.llm.primary.base_url) == 3
        called.clear()
        # теперь primary пропущен мгновенно, fallback сразу работает
        res = call_llm("sys", "usr", max_tokens=50)
        assert res["source"] == "fallback"
        assert called.count(cfg.llm.primary.base_url) == 0