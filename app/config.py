"""Centralized configuration loader. All env vars accessed via settings.X."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    # Telegram
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_WEBHOOK_SECRET: str

    # Authorization
    AUTHORIZED_TELEGRAM_USER_ID: int

    # Supabase
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str

    # Anthropic (optional in Phase 1)
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL: str = "claude-sonnet-4-5"

    # GHL (optional in Phase 1)
    GHL_PRIVATE_INTEGRATION_TOKEN: str = ""
    GHL_LOCATION_ID: str = ""
    GHL_WRITE_MODE: str = "dry_run"  # "dry_run" or "live"
    GMAIL_WRITE_MODE: str = "draft"  # "draft" or "live"

    # Google (optional in Phase 1)
    GOOGLE_OAUTH_CLIENT_ID: str = ""
    GOOGLE_OAUTH_CLIENT_SECRET: str = ""
    GOOGLE_OAUTH_REDIRECT_URI: str = "http://localhost:8000/auth/google/callback"

    # App
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    PUBLIC_BASE_URL: str = "http://localhost:8000"


settings = Settings()