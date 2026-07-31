from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root .env (…/kronostrader/.env), then local override
_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"
_LOCAL_ENV = Path(__file__).resolve().parents[1] / ".env"
_ENV_FILES = tuple(
    str(p) for p in (_ROOT_ENV, _LOCAL_ENV) if p.is_file()
) or (".env",)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    kronos_model_size: Literal["small", "base", "mini"] = "base"
    max_context: int = 512
    use_gpu: bool = False
    inference_host: str = "0.0.0.0"
    inference_port: int = 8000
    log_level: str = "INFO"

    @property
    def model_id(self) -> str:
        return {
            "small": "NeoQuasar/Kronos-small",
            "base": "NeoQuasar/Kronos-base",
            "mini": "NeoQuasar/Kronos-mini",
        }[self.kronos_model_size]

    @property
    def tokenizer_id(self) -> str:
        if self.kronos_model_size == "mini":
            return "NeoQuasar/Kronos-Tokenizer-2k"
        return "NeoQuasar/Kronos-Tokenizer-base"

    @property
    def device(self) -> str:
        if self.use_gpu:
            return "cuda:0"
        return "cpu"


@lru_cache
def get_settings() -> Settings:
    return Settings()
