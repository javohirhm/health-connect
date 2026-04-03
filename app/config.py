"""Application configuration from environment variables."""
from __future__ import annotations

import os
from typing import List
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


class Config:
    # Database
    DB_TYPE: str = os.getenv("DB_TYPE", "sqlite")
    DB_PATH: str = os.getenv("DB_PATH", "health_data.db")
    PG_HOST: str = os.getenv("PG_HOST", "localhost")
    PG_PORT: int = int(os.getenv("PG_PORT", "5432"))
    PG_USER: str = os.getenv("PG_USER", "healthconnect")
    PG_PASSWORD: str = os.getenv("PG_PASSWORD", "changeme")
    PG_DATABASE: str = os.getenv("PG_DATABASE", "healthconnect")

    # Server
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    RELOAD: bool = os.getenv("RELOAD", "false").lower() == "true"
    WORKERS: int = int(os.getenv("WORKERS", "1"))

    # CORS
    CORS_ORIGINS: List[str] = os.getenv("CORS_ORIGINS", "*").split(",")

    # ML Models
    MODELS_DIR: str = os.getenv("MODELS_DIR", str(Path(__file__).parent.parent / "models"))

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    @property
    def pg_url(self) -> str:
        return f"postgresql://{self.PG_USER}:{self.PG_PASSWORD}@{self.PG_HOST}:{self.PG_PORT}/{self.PG_DATABASE}"

    @property
    def db_path_resolved(self) -> Path:
        p = Path(self.DB_PATH)
        if not p.is_absolute():
            p = Path(__file__).parent.parent / p
        return p


config = Config()
