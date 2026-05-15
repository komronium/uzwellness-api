from functools import lru_cache
from typing import Literal

from pydantic import PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    PROJECT_NAME: str = "UzWellness API"
    API_PREFIX: str = "/api"
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"
    DEBUG: bool = True

    DATABASE_URL: PostgresDsn
    TEST_DATABASE_URL: PostgresDsn | None = None
    REDIS_URL: RedisDsn

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "https://uzwellness.com",
        "https://www.uzwellness.com",
    ]

    INITIAL_SUPER_ADMIN_EMAIL: str | None = None
    INITIAL_SUPER_ADMIN_PASSWORD: str | None = None

    UPLOAD_DIR: str = "uploads"
    UPLOAD_URL_PREFIX: str = "/uploads"
    MAX_UPLOAD_SIZE_MB: int = 10

    # Payment provider configuration (production values come from .env)
    PAYME_CHECKOUT_URL: str = "https://checkout.paycom.uz/"
    PAYME_MERCHANT_ID: str = ""
    PAYME_MERCHANT_KEY: str = ""  # used for HMAC webhook verification
    CLICK_CHECKOUT_URL: str = "https://my.click.uz/services/pay"
    CLICK_SERVICE_ID: str = ""
    CLICK_MERCHANT_ID: str = ""
    CLICK_SECRET_KEY: str = ""  # used for webhook signature verification

    # Outbound email
    EMAIL_FROM: str = "noreply@uzwellness.com"
    EMAIL_BACKEND: str = "log"  # "log" or "smtp"
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_USE_TLS: bool = True

    # Rate limiting
    RATE_LIMIT_ENABLED: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
