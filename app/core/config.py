from functools import lru_cache
from typing import Literal

from pydantic import PostgresDsn, RedisDsn, field_validator, model_validator
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

    # Uzum Bank Merchant API. The customer pays inside the Uzum Bank app and
    # Uzum calls our /payments/uzum/* webhooks, authenticated with Basic auth.
    # Credentials and serviceId are agreed with Uzum (we pick them for testing,
    # Uzum issues the production serviceId afterwards).
    UZUM_SERVICE_ID: int = 0
    UZUM_MERCHANT_USERNAME: str = ""
    UZUM_MERCHANT_PASSWORD: str = ""
    # A created transaction that is never confirmed expires after this many
    # minutes (Uzum's protocol fixes this at 30).
    UZUM_TRANSACTION_TIMEOUT_MINUTES: int = 30

    # Uzum Checkout — the card-payment gateway on our own site. Unlike the
    # Merchant API above, *we* call Uzum (`/payment/register`) and the guest is
    # sent to the returned payment page. Terminal id and API key are issued by
    # Uzum per environment; while they are empty the endpoints answer 503.
    UZUM_CHECKOUT_API_URL: str = "https://test-chk-api.uzumcheckout.uz"
    UZUM_CHECKOUT_TERMINAL_ID: str = ""
    UZUM_CHECKOUT_API_KEY: str = ""
    UZUM_CHECKOUT_TIMEOUT_SECONDS: float = 20.0
    # Where Uzum sends the guest's browser once the form is finished.
    UZUM_CHECKOUT_SUCCESS_URL: str = "https://uzwellness.com/payment/success"
    UZUM_CHECKOUT_FAILURE_URL: str = "https://uzwellness.com/payment/failure"
    # How long the payment form stays open. Uzum allows 600..1800 seconds.
    UZUM_CHECKOUT_SESSION_TIMEOUT_SECS: int = 900
    # Auto-fiscalization is a per-terminal switch on Uzum's side. When it is on
    # (the default on our test terminal) every /payment/register must carry a
    # cart with the tax data below, or Uzum answers 3045.
    UZUM_CHECKOUT_AUTOFISCALIZATION: bool = True
    # Merchant INN and the catalogue codes of the service we sell, from
    # https://tasnif.soliq.uz — Uzum validates both against the catalogue.
    UZUM_CHECKOUT_TIN: str = ""
    UZUM_CHECKOUT_SPIC: str = ""
    UZUM_CHECKOUT_PACKAGE_CODE: str = ""
    UZUM_CHECKOUT_VAT_PERCENT: int = 0

    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    # Callback registered in Google Cloud Console, e.g.
    # https://api.uzwellness.com/api/auth/google/callback
    GOOGLE_REDIRECT_URI: str = ""
    # Frontend page that receives the access token in the URL fragment after login
    OAUTH_FRONTEND_REDIRECT_URL: str = "https://uzwellness.com/auth/callback"

    # EMAIL_BACKEND: "log" (print only), "smtp", or "resend" (HTTPS API on 443 —
    # use this when the host blocks outbound SMTP ports).
    EMAIL_FROM: str = "noreply@uzwellness.com"
    EMAIL_BACKEND: str = "log"
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_USE_TLS: bool = True
    # Implicit SSL (port 465). TimeWeb domain mailboxes use this; when true the
    # client connects over SSL directly instead of upgrading via STARTTLS.
    SMTP_USE_SSL: bool = False
    # Every send runs on a two-thread pool, so a mail host that accepts the TCP
    # connection and then stops answering would park both threads forever and
    # silently stop all booking and cancellation email. Never leave this unset.
    SMTP_TIMEOUT_SECONDS: float = 20.0
    RESEND_API_KEY: str | None = None

    # Booking voucher PDF
    VOUCHER_BRAND_NAME: str = "UzWellness"
    # Optional TTF overrides; otherwise Ubuntu/DejaVu are auto-detected.
    VOUCHER_FONT_PATH: str = ""
    VOUCHER_FONT_BOLD_PATH: str = ""

    # Printed on the voucher as the platform contact (the property's own phone
    # and email are printed next to it).
    SUPPORT_EMAIL: str = "support@uzwellness.com"
    SUPPORT_PHONE: str = ""

    EXCHANGE_RATE_SYNC_ENABLED: bool = True
    EXCHANGE_RATE_SYNC_INTERVAL_HOURS: int = 6
    EXCHANGE_RATE_SYNC_CURRENCIES: list[str] = ["USD", "EUR", "RUB", "KZT"]

    RATE_LIMIT_ENABLED: bool = True
    # Peers whose X-Forwarded-For header may be believed. In production the app
    # listens on 127.0.0.1 and only nginx can reach it, so without this every
    # request looks like it comes from the proxy and the whole site shares one
    # rate-limit bucket — ten failed logins would lock out every guest at once.
    TRUSTED_PROXY_IPS: list[str] = ["127.0.0.1", "::1"]

    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_RECYCLE_SECONDS: int = 3600

    @field_validator(
        "UZUM_CHECKOUT_TERMINAL_ID",
        "UZUM_CHECKOUT_API_KEY",
        "UZUM_CHECKOUT_TIN",
        "UZUM_CHECKOUT_SPIC",
        "UZUM_CHECKOUT_PACKAGE_CODE",
        mode="after",
    )
    @classmethod
    def strip_inline_comment(cls, value: str) -> str:
        """Drop a trailing ``# ...`` note and surrounding whitespace.

        ``.env`` files are edited by hand on the server, and dotenv only treats
        ``#`` as a comment when a space precedes it — ``SPIC=1020...# сутки``
        otherwise reaches Uzum as part of the code and is rejected mid-payment.
        These fields are opaque identifiers that never legitimately contain
        ``#``, so stripping one here turns a silent outage into a no-op.
        """

        return value.split("#", 1)[0].strip()

    @property
    def uzum_checkout_enabled(self) -> bool:
        """Both credentials present — otherwise Checkout stays switched off."""

        return bool(self.UZUM_CHECKOUT_TERMINAL_ID and self.UZUM_CHECKOUT_API_KEY)

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if self.ENVIRONMENT != "production":
            return self

        errors: list[str] = []
        if self.DEBUG:
            errors.append("DEBUG must be false in production")
        if len(self.JWT_SECRET_KEY) < 32:
            errors.append("JWT_SECRET_KEY must be at least 32 characters in production")
        if self.UZUM_SERVICE_ID and not (
            self.UZUM_MERCHANT_USERNAME and self.UZUM_MERCHANT_PASSWORD
        ):
            errors.append(
                "UZUM_MERCHANT_USERNAME and UZUM_MERCHANT_PASSWORD are required "
                "when Uzum is enabled"
            )
        if (
            self.UZUM_MERCHANT_USERNAME or self.UZUM_MERCHANT_PASSWORD
        ) and not self.UZUM_SERVICE_ID:
            errors.append("UZUM_SERVICE_ID is required when Uzum credentials are set")
        if self.uzum_checkout_enabled and self.UZUM_CHECKOUT_AUTOFISCALIZATION:
            missing = [
                name
                for name, value in (
                    ("UZUM_CHECKOUT_TIN", self.UZUM_CHECKOUT_TIN),
                    ("UZUM_CHECKOUT_SPIC", self.UZUM_CHECKOUT_SPIC),
                    ("UZUM_CHECKOUT_PACKAGE_CODE", self.UZUM_CHECKOUT_PACKAGE_CODE),
                )
                if not value
            ]
            if missing:
                errors.append(
                    f"{', '.join(missing)} are required when Uzum Checkout "
                    "auto-fiscalization is enabled"
                )
        if not 600 <= self.UZUM_CHECKOUT_SESSION_TIMEOUT_SECS <= 1800:
            errors.append(
                "UZUM_CHECKOUT_SESSION_TIMEOUT_SECS must be between 600 and 1800"
            )
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
        if self.EMAIL_BACKEND == "resend" and not self.RESEND_API_KEY:
            errors.append("RESEND_API_KEY is required when EMAIL_BACKEND=resend")
        if self.EMAIL_BACKEND == "log":
            # The default backend only writes to the log. In production that
            # means booking confirmations and cancellation codes are never
            # sent and nobody notices — every guest just waits for an email
            # that will not arrive.
            errors.append(
                "EMAIL_BACKEND must be 'smtp' or 'resend' in production; "
                "'log' silently discards every booking and cancellation email"
            )
        if "*" in self.CORS_ORIGINS:
            # With allow_credentials=True a wildcard origin is both rejected by
            # browsers and a session-theft risk if it ever were honoured.
            errors.append("CORS_ORIGINS must list exact origins, never '*'")
        insecure_origins = [
            origin for origin in self.CORS_ORIGINS if origin.startswith("http://")
        ]
        if insecure_origins:
            errors.append(
                f"CORS_ORIGINS must be https in production: {', '.join(insecure_origins)}"
            )
        if errors:
            raise ValueError("; ".join(errors))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
