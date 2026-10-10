"""
app/core/config.py – Application Settings & Constants.
WHAT IT DOES:
  Loads configuration from environment variables (.env) with Pydantic Settings
  and defines mill constants (roles, stages, rates, wastage).
WHY IT EXISTS:
  Centralizes database connection URLs, secret keys, and manufacturing rules
  so they can be managed securely across local, Docker, and Neon environments.
"""

import os
try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ImportError:
    from pydantic import BaseSettings
    SettingsConfigDict = None


class Settings(BaseSettings):
    """
    WHAT: Global typed settings for Warpspeed.
    WHY: Validates environment variables at startup and provides defaults.
    """
    APP_NAME: str = "Warpspeed Mini-ERP"
    APP_ENV: str = "development"
    SECRET_KEY: str = "warpspeed-super-secret-key-change-in-production-2026"
    SESSION_COOKIE_NAME: str = "warpspeed_session"

    # Database URL: Supports PostgreSQL (Neon/Docker) with local SQLite fallback
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "sqlite:///./warpspeed_fastapi.db"
    )

    # Manufacturing Constants
    ROLL_LENGTH_M: float = 50.0       # Standard roll length in meters
    WASTAGE_RATE: float = 0.08         # 8% standard yarn wastage during processing
    WAGE_RATE_PER_HOUR: float = 120.0  # INR 120 per machine-hour
    OVERHEAD_RATE_PER_HOUR: float = 50.0 # INR 50 per machine-hour

    # Roles
    ROLE_OWNER: str = "OWNER"
    ROLE_FLOOR: str = "FLOOR"
    ROLE_BUYER: str = "BUYER"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
