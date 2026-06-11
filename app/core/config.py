from functools import lru_cache
from typing import Literal

from pydantic import PostgresDsn, RedisDsn, model_validator
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
    DEBUG: bool = False

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
    MAX_UPLOAD_SIZE_MB: int = 50
    IMAGE_MAX_PIXELS: int = 64_000_000
    IMAGE_MAX_DIMENSION: int = 1920
    IMAGE_WEBP_QUALITY: int = 85

    PAYME_CHECKOUT_URL: str = "https://checkout.paycom.uz/"
    PAYME_MERCHANT_ID: str = ""
    PAYME_MERCHANT_KEY: str = ""
    CLICK_CHECKOUT_URL: str = "https://my.click.uz/services/pay"
    CLICK_SERVICE_ID: str = ""
    CLICK_MERCHANT_ID: str = ""
    CLICK_SECRET_KEY: str = ""

    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    # Callback registered in Google Cloud Console, e.g.
    # https://api.uzwellness.com/api/auth/google/callback
    GOOGLE_REDIRECT_URI: str = ""
    # Frontend page that receives tokens in the URL fragment after login
    OAUTH_FRONTEND_REDIRECT_URL: str = "https://uzwellness.com/auth/callback"

    EMAIL_FROM: str = "noreply@uzwellness.com"
    EMAIL_BACKEND: str = "log"
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_USE_TLS: bool = True

    EXCHANGE_RATE_SYNC_ENABLED: bool = True
    EXCHANGE_RATE_SYNC_INTERVAL_HOURS: int = 6
    EXCHANGE_RATE_SYNC_CURRENCIES: list[str] = ["USD", "EUR", "RUB", "KZT"]

    RATE_LIMIT_ENABLED: bool = True
    TRUSTED_PROXY_IPS: list[str] = []

    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_RECYCLE_SECONDS: int = 3600

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if self.ENVIRONMENT != "production":
            return self

        errors: list[str] = []
        if self.DEBUG:
            errors.append("DEBUG must be false in production")
        if len(self.JWT_SECRET_KEY) < 32:
            errors.append("JWT_SECRET_KEY must be at least 32 characters in production")
        if self.PAYME_MERCHANT_ID and not self.PAYME_MERCHANT_KEY:
            errors.append("PAYME_MERCHANT_KEY is required when Payme is enabled")
        if self.CLICK_SERVICE_ID and not self.CLICK_SECRET_KEY:
            errors.append("CLICK_SECRET_KEY is required when Click is enabled")
        if self.GOOGLE_CLIENT_ID and not (
            self.GOOGLE_CLIENT_SECRET and self.GOOGLE_REDIRECT_URI
        ):
            errors.append(
                "GOOGLE_CLIENT_SECRET and GOOGLE_REDIRECT_URI are required "
                "when Google OAuth is enabled"
            )
        if self.EMAIL_BACKEND == "smtp" and (
            not self.SMTP_HOST or not self.SMTP_USERNAME or not self.SMTP_PASSWORD
        ):
            errors.append(
                "SMTP_HOST, SMTP_USERNAME and SMTP_PASSWORD are required for SMTP"
            )
        if errors:
            raise ValueError("; ".join(errors))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
