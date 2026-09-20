from __future__ import annotations

import os
import shutil
import sys
import tomllib
from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

PKG_DIR = Path(__file__).resolve().parent
DEFAULTS_DIR = PKG_DIR / "defaults"
_REPO_ROOT = PKG_DIR.parents[1]  # checkout: src/spendtrack -> корень репо; wheel: .../Lib
ROOT = _REPO_ROOT  # legacy-алиас: dev-скрипты и тесты (в установленном пакете не используется)
_REPO_CONFIG_DIR = _REPO_ROOT / "config"
CONFIG_DIR = _REPO_CONFIG_DIR  # legacy-алиас (repo-режим)


class LLMEndpoint(BaseModel):
    base_url: str
    model: str


class LLMSettings(BaseModel):
    primary: LLMEndpoint
    fallback: LLMEndpoint
    deepseek: LLMEndpoint
    offline: LLMEndpoint
    max_tokens: int = 400


class AcceptanceSettings(BaseModel):
    auto_accept_confidence: float = 0.9


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SPENDTRACK_", env_file=".env", extra="ignore")

    port: int = 8766
    llm: LLMSettings
    acceptance: AcceptanceSettings = AcceptanceSettings()
    db_path: Path | None = None
    freel_llm_api_key: str = ""
    openrouter_api_key: str = ""
    # BYO-LLM: свой OpenAI-совместимый сервер (ключ/эндпоинт задаёт пользователь).
    llm_provider: str = ""
    llm_base_url: str = ""
    llm_model: str = ""
    llm_api_key: str = ""


def _repo_config() -> Path:
    return _REPO_CONFIG_DIR


def repo_mode() -> bool:
    """Repo-режим: рядом есть config/settings.toml (git clone + uv sync, прод NSSM).

    В установленном пакете (uv tool/uvx) конфига в пакете нет — данные/конфиг идут в user-dir.
    """
    return (_repo_config() / "settings.toml").is_file()


def user_config_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming"
        return Path(base) / "spendtrack"
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "spendtrack"


def user_data_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
        return Path(base) / "spendtrack"
    base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(base) / "spendtrack"


def resolve_config_dir() -> Path:
    """Приоритет: SPENDTRACK_CONFIG_DIR → config/ репозитория → user-config (APPDATA/XDG)."""
    env = os.environ.get("SPENDTRACK_CONFIG_DIR")
    if env:
        return Path(env).expanduser()
    if repo_mode():
        return _repo_config()
    return user_config_dir()


def resolve_data_dir() -> Path:
    """Приоритет: SPENDTRACK_DATA_DIR → data/ репозитория → user-data (LOCALAPPDATA/XDG)."""
    env = os.environ.get("SPENDTRACK_DATA_DIR")
    if env:
        return Path(env).expanduser()
    if repo_mode():
        return _REPO_ROOT / "data"
    return user_data_dir()


def _atomic_copy(src: Path, dest: Path) -> None:
    """Копия через временный файл + replace: читатель не увидит недописанный файл."""
    tmp = dest.with_name(dest.name + ".tmp")
    try:
        shutil.copyfile(src, tmp)
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)


def ensure_config_dir() -> Path:
    """Каталог конфига, готовый к записи; в не-repo режиме копирует пакетные дефолты.

    Идемпотентно: существующие файлы не перезаписываются (правки пользователя важнее);
    копирование атомарное (UI/сервер могут читать файл параллельно).
    """
    target = resolve_config_dir()
    if target == _repo_config() and repo_mode():
        return target
    target.mkdir(parents=True, exist_ok=True)
    for name in ("settings.toml", "taxonomy.toml"):
        dest = target / name
        if not dest.exists():
            _atomic_copy(DEFAULTS_DIR / name, dest)
    return target


def load_settings(config_dir: Path | None = None) -> Settings:
    base = Path(config_dir) if config_dir else resolve_config_dir()
    path = base / "settings.toml"
    if not path.is_file():
        path = DEFAULTS_DIR / "settings.toml"  # установленный режим: дефолт из пакета
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return Settings(**data)


def settings() -> Settings:
    return load_settings()


def paths_info() -> dict:
    """Текущая раскладка (диагностика `spendtrack paths` и поддержка)."""
    cfg = load_settings()
    db = cfg.db_path or (resolve_data_dir() / "spend.db")
    return {
        "mode": "repo" if repo_mode() else "installed",
        "package": str(PKG_DIR),
        "config_dir": str(resolve_config_dir()),
        "data_dir": str(resolve_data_dir()),
        "db_path": str(db),
    }
