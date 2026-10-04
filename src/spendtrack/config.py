from __future__ import annotations

import os
import re
import shutil
import sys
import tomllib
from pathlib import Path

from pydantic import BaseModel, field_validator
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

    @classmethod
    def settings_customise_sources(
        cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings,
    ):
        """S6 (Astra 01.10): env выше TOML-значений, переданных через init.

        По умолчанию pydantic-settings ставит init выше env — из-за этого `SPENDTRACK_DB_PATH`
        не переопределял `db_path` из settings.toml, и команды работали не с той БД (опасно
        при диагностике/спасении данных, когда пользователь явно указал другую БД).
        """
        return (env_settings, dotenv_settings, init_settings, file_secret_settings)

    port: int = 8766
    # Ф0 «Беларусь/BYN»: валюта, в которой считаются итоги/бюджеты/дайджест (ISO 4217, default RUB).
    base_currency: str = "RUB"
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

    @field_validator("base_currency")
    @classmethod
    def _base_currency_iso(cls, v: str) -> str:
        code = str(v).strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", code):
            raise ValueError("base_currency: ожидается код ISO 4217 (3 латинские буквы, напр. RUB/BYN)")
        return code


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


def resolve_db_path(settings_obj: Settings | None = None) -> Path:
    """Единая точка пути к БД: cfg.db_path (env-aware) → data_dir/spend.db; expanduser + resolve.

    C2/S3 (тикеты 03.10): убирает третий дефолт (legacy ROOT) и cwd-зависимость в backup/doctor/drill —
    относительный путь всегда указывает на один и тот же файл, откуда бы ни запускали.
    """
    cfg = settings_obj or load_settings()
    if cfg.db_path:
        return Path(cfg.db_path).expanduser().resolve()
    return (resolve_data_dir() / "spend.db").resolve()


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


def _deep_merge(base: dict, user: dict) -> dict:
    """Рекурсивный merge: пользовательские значения поверх пакетных дефолтов (S1, 03.10)."""
    out = dict(base)
    for key, value in user.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_settings(config_dir: Path | None = None) -> Settings:
    """Настройки: пакетные дефолты ← пользовательский settings.toml (merge; S1, 03.10).

    Неполный файл (нет секции/ключа) больше не роняет команды: недостающее берётся из
    `src/spendtrack/defaults/settings.toml`. Синтаксически битый TOML — по-прежнему ошибка
    (её явно показывают `doctor` как `settings_config: critical` и `paths` — раскладка без Settings).
    """
    base = Path(config_dir) if config_dir else resolve_config_dir()
    path = base / "settings.toml"
    user_data: dict = {}
    if path.is_file():
        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):  # BOM от Windows-редакторов (S1, 03.10) — tomllib его не глотает
            raw = raw[3:]
        user_data = tomllib.loads(raw.decode("utf-8"))
    defaults_path = DEFAULTS_DIR / "settings.toml"
    defaults: dict = {}
    if defaults_path.is_file():
        with open(defaults_path, "rb") as f:
            defaults = tomllib.load(f)
    return Settings(**_deep_merge(defaults, user_data))


_base_cache: dict[str, object] = {"key": None, "value": "RUB"}


def base_currency() -> str:
    """Базовая валюта установки (ISO 4217): в ней считаются итоги/бюджеты/дайджест.

    Кэш по (settings.toml, env SPENDTRACK_BASE_CURRENCY, mtime): горячие пути (fmt_money на каждую
    строку, импорт, fingerprint) не перечитывают TOML; правка настроек/env подхватывается без
    перезапуска — ключ кэша меняется.
    """
    path = resolve_config_dir() / "settings.toml"
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        mtime = 0
    key = (str(path), os.environ.get("SPENDTRACK_BASE_CURRENCY", ""), mtime)
    if _base_cache["key"] != key:
        # Сначала вычисляем значение: при ошибке конфига кэш не «отравляется» стухшим значением
        # (ревью wave5, S1) — следующий вызов снова честно упадёт, а не вернёт старую базу.
        value = load_settings().base_currency
        _base_cache["key"] = key
        _base_cache["value"] = value
    return str(_base_cache["value"])


def settings() -> Settings:
    return load_settings()


def paths_info() -> dict:
    """Раскладка (диагностика `spendtrack paths`): не зависит от читаемости settings.toml (S1, 03.10)."""
    info = {
        "mode": "repo" if repo_mode() else "installed",
        "package": str(PKG_DIR),
        "config_dir": str(resolve_config_dir()),
        "data_dir": str(resolve_data_dir()),
    }
    try:
        info["db_path"] = str(resolve_db_path())
    except Exception as e:  # noqa: BLE001 — битый settings.toml не должен ломать диагностику
        info["db_path"] = str(resolve_data_dir() / "spend.db")
        info["db_note"] = f"settings.toml не читается: {e}"
    return info
