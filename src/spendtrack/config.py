from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"


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
    model_config = SettingsConfigDict(env_prefix="SPENDTRACK_", extra="ignore")

    port: int = 8766
    llm: LLMSettings
    acceptance: AcceptanceSettings = AcceptanceSettings()
    db_path: Path | None = None
    freel_llm_api_key: str = ""
    openrouter_api_key: str = ""


def load_settings(config_dir: Path | None = None) -> Settings:
    config_dir = config_dir or CONFIG_DIR
    with open(config_dir / "settings.toml", "rb") as f:
        data = tomllib.load(f)
    return Settings(**data)


def settings() -> Settings:
    return load_settings()
