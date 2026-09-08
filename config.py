"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    database_path: Path = Path(os.getenv("DATABASE_PATH", "./data/investment.db"))
    default_start_date: str = os.getenv("DEFAULT_START_DATE", "2010-01-01")
    market_data_provider: str = os.getenv("MARKET_DATA_PROVIDER", "nasdaq").lower()
    market_api_key: str = os.getenv("MARKET_API_KEY", "")
    market_api_secret: str = os.getenv("MARKET_API_SECRET", "")
    http_timeout: float = float(os.getenv("HTTP_TIMEOUT", "30"))

    def resolved_database_path(self) -> Path:
        path = self.database_path
        return path if path.is_absolute() else BASE_DIR / path


settings = Settings()
