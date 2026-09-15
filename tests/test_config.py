from __future__ import annotations

from spendtrack.config import ROOT, load_settings


def test_env_file_loaded(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("SPENDTRACK_OPENROUTER_API_KEY=sk-or-test\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SPENDTRACK_OPENROUTER_API_KEY", raising=False)
    assert load_settings(ROOT / "config").openrouter_api_key == "sk-or-test"


def test_env_var_beats_env_file(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("SPENDTRACK_FREEL_LLM_API_KEY=from-dotenv\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SPENDTRACK_FREEL_LLM_API_KEY", "from-env")
    assert load_settings(ROOT / "config").freel_llm_api_key == "from-env"
