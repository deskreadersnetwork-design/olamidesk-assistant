"""
config.py — Central configuration loader.

Reads every environment variable once, validates it, and exposes
typed, ready-to-use settings to the rest of the app.

If a required variable is missing, the app refuses to start and
prints exactly which variable is missing. This is safer than
running with empty secrets and failing later in confusing ways.
"""

import os
import logging
from dataclasses import dataclass

from dotenv import load_dotenv

# Load .env file if it exists (for local development only).
# On Railway, environment variables are injected directly; this call is harmless.
load_dotenv()


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _get_required(name: str) -> str:
    """Fetch a required env var or raise a clear error."""
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(
            f"Missing required environment variable: {name}. "
            f"Set it in your .env file (local) or Railway variables (production)."
        )
    return value


def _get_int(name: str, default: int) -> int:
    """Fetch an integer env var with a default; raise if it is not a number."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"Environment variable {name} must be an integer, got: {raw!r}") from exc


@dataclass(frozen=True)
class Settings:
    """Immutable container for all app settings."""
    telegram_bot_token: str
    bot_username: str
    admin_telegram_id: int
    support_username: str
    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_model: str
    database_url: str
    max_history_messages: int
    rate_limit_seconds: int
    log_level: str


def load_settings() -> Settings:
    """Load and validate all settings. Called once in main.py."""
    admin_raw = _get_required("ADMIN_TELEGRAM_ID")
    try:
        admin_id = int(admin_raw)
    except ValueError as exc:
        raise ConfigError(
            f"ADMIN_TELEGRAM_ID must be a numeric Telegram user ID, got: {admin_raw!r}"
        ) from exc

    settings = Settings(
        telegram_bot_token=_get_required("TELEGRAM_BOT_TOKEN"),
        bot_username=os.getenv("BOT_USERNAME", "").strip().lstrip("@"),
        admin_telegram_id=admin_id,
        support_username=os.getenv("SUPPORT_USERNAME", "").strip().lstrip("@"),
        deepseek_api_key=_get_required("DEEPSEEK_API_KEY"),
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip().rstrip("/"),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip(),
        database_url=_get_required("DATABASE_URL"),
        max_history_messages=_get_int("MAX_HISTORY_MESSAGES", 20),
        rate_limit_seconds=_get_int("RATE_LIMIT_SECONDS", 3),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
    )

    # Configure logging based on the loaded level.
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    return settings
