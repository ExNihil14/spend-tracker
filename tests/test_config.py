from __future__ import annotations

from pathlib import Path

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


def test_resolve_db_path_relative_is_resolved_from_cwd(tmp_path, monkeypatch):
    """C2/S3: единая точка пути к БД — SPENDTRACK_DB_PATH резолвится в абсолютный (cwd-независимость)."""
    from spendtrack.config import resolve_db_path

    monkeypatch.chdir(tmp_path)
    (tmp_path / "sub").mkdir()
    monkeypatch.setenv("SPENDTRACK_DB_PATH", "sub/spend.db")
    assert resolve_db_path() == (tmp_path / "sub" / "spend.db").resolve()


def test_default_db_path_is_single_source(tmp_path, monkeypatch):
    """S3/C2: `backup.default_db_path` — та же единая точка, что `resolve_db_path` (без своего дефолта)."""
    from spendtrack.backup import default_db_path
    from spendtrack.config import resolve_db_path

    monkeypatch.setenv("SPENDTRACK_DB_PATH", str(tmp_path / "x.db"))
    assert default_db_path() == resolve_db_path()


SETTINGS_TOML = """db_path = "A.db"
port = 8766
[llm]
[llm.primary]
base_url = "https://openrouter.ai/api/v1"
model = "m"
[llm.fallback]
base_url = "http://localhost:3001/v1"
model = "m"
[llm.deepseek]
base_url = "http://127.0.0.1:3201/v1"
model = "m"
[llm.offline]
base_url = "http://127.0.0.1:11434/v1"
model = "m"
[acceptance]
auto_accept_confidence = 0.9
"""


def test_env_overrides_toml_db_path(tmp_path, monkeypatch):
    """S6 (Astra 01.10): SPENDTRACK_DB_PATH переопределяет db_path из settings.toml.

    По умолчанию pydantic-settings ставит init (TOML) выше env — команды работали не с той БД,
    даже когда пользователь явно указал другую.
    """
    (tmp_path / "settings.toml").write_text(SETTINGS_TOML, encoding="utf-8")
    monkeypatch.setenv("SPENDTRACK_DB_PATH", "B.db")
    cfg = load_settings(config_dir=tmp_path)
    assert Path(cfg.db_path).name == "B.db"


def test_toml_used_when_env_absent(tmp_path, monkeypatch):
    """Без env-переменной значение из TOML остаётся источником."""
    (tmp_path / "settings.toml").write_text(SETTINGS_TOML, encoding="utf-8")
    monkeypatch.delenv("SPENDTRACK_DB_PATH", raising=False)
    cfg = load_settings(config_dir=tmp_path)
    assert Path(cfg.db_path).name == "A.db"
