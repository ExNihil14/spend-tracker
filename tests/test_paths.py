from __future__ import annotations

import sys

from spendtrack import config
from spendtrack.store import Store
from spendtrack.taxonomy import load_taxonomy


def test_repo_mode_keeps_repo_paths():
    assert config.repo_mode() is True
    assert config.resolve_config_dir() == config.ROOT / "config"
    assert config.resolve_data_dir() == config.ROOT / "data"


def test_env_overrides_win(tmp_path, monkeypatch):
    cfg_dir, data_dir = tmp_path / "cfg", tmp_path / "data"
    monkeypatch.setenv("SPENDTRACK_CONFIG_DIR", str(cfg_dir))
    monkeypatch.setenv("SPENDTRACK_DATA_DIR", str(data_dir))
    assert config.resolve_config_dir() == cfg_dir
    assert config.resolve_data_dir() == data_dir


def test_installed_mode_uses_user_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "_repo_config", lambda: tmp_path / "no-repo" / "config")
    monkeypatch.delenv("SPENDTRACK_CONFIG_DIR", raising=False)
    monkeypatch.delenv("SPENDTRACK_DATA_DIR", raising=False)
    if sys.platform == "win32":
        monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
        assert config.resolve_config_dir() == tmp_path / "roaming" / "spendtrack"
        assert config.resolve_data_dir() == tmp_path / "local" / "spendtrack"
    else:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-cfg"))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
        assert config.resolve_config_dir() == tmp_path / "xdg-cfg" / "spendtrack"
        assert config.resolve_data_dir() == tmp_path / "xdg-data" / "spendtrack"
    assert config.repo_mode() is False
    assert config.paths_info()["mode"] == "installed"


def test_load_settings_falls_back_to_packaged_default(tmp_path, monkeypatch):
    monkeypatch.setenv("SPENDTRACK_CONFIG_DIR", str(tmp_path / "empty"))
    monkeypatch.delenv("SPENDTRACK_PORT", raising=False)
    cfg = config.load_settings()
    assert cfg.port == 8766
    assert cfg.llm.primary.base_url.startswith("https://")


def test_load_taxonomy_falls_back_to_packaged_default(tmp_path, monkeypatch):
    monkeypatch.setenv("SPENDTRACK_CONFIG_DIR", str(tmp_path / "empty"))
    tax = load_taxonomy()
    assert len(tax.categories) == 18
    assert tax.is_valid("groceries")


def test_ensure_config_dir_materializes_defaults_once(tmp_path, monkeypatch):
    target = tmp_path / "cfg"
    monkeypatch.setenv("SPENDTRACK_CONFIG_DIR", str(target))
    assert config.ensure_config_dir() == target
    assert (target / "settings.toml").is_file()
    assert (target / "taxonomy.toml").is_file()
    edited = target / "taxonomy.toml"
    edited.write_text("# правка пользователя\n", encoding="utf-8")
    config.ensure_config_dir()
    assert edited.read_text(encoding="utf-8") == "# правка пользователя\n"


def test_store_default_path_uses_data_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # .env из cwd не подмешивается
    monkeypatch.setenv("SPENDTRACK_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("SPENDTRACK_DB_PATH", raising=False)
    store = Store()
    try:
        assert store.path == tmp_path / "data" / "spend.db"
        assert store.path.is_file()
    finally:
        store.close()
