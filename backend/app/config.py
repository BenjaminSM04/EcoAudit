"""Configuración por variables de entorno (prefijo ``ECOAUDIT_``)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_SECRET = "dev-only-secret-change-me-before-any-deployment"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ECOAUDIT_", env_file=".env", extra="ignore")

    environment: str = "dev"  # dev | prod
    database_url: str = "sqlite:///./data/ecoaudit.db"
    storage_dir: Path = Path("./data/storage")
    secret_key: str = _DEV_SECRET
    access_token_minutes: int = 480
    cors_origins: str = "http://localhost:5173"
    max_upload_mb: int = 25
    # True: el análisis corre dentro del proceso de la API (cómodo en desarrollo).
    # False: lo toma un proceso aparte (`python -m app.worker`).
    inline_worker: bool = True
    worker_poll_seconds: float = 1.0
    # Un análisis ``running`` más antiguo que esto se considera interrumpido y se reencola.
    analysis_timeout_seconds: int = 300

    @model_validator(mode="after")
    def _no_default_secret_outside_dev(self) -> Settings:
        if self.environment != "dev" and self.secret_key == _DEV_SECRET:
            raise ValueError("ECOAUDIT_SECRET_KEY debe definirse fuera del entorno dev.")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
