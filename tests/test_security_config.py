from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.core.rate_limit import _client_ip


def _base_settings(**overrides):
    payload = {
        "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/app",
        "REDIS_URL": "redis://localhost:6379/0",
        "JWT_SECRET_KEY": "x" * 32,
    }
    payload.update(overrides)
    return Settings(_env_file=None, **payload)


def _production_settings(**overrides):
    """Production defaults that already satisfy the mandatory-config checks."""

    payload = {
        "ENVIRONMENT": "production",
        "EMAIL_BACKEND": "resend",
        "RESEND_API_KEY": "re_test_key",
        "CORS_ORIGINS": ["https://uzwellness.com"],
    }
    payload.update(overrides)
    return _base_settings(**payload)


def test_forwarded_for_is_ignored_without_trusted_proxy():
    saved = settings.TRUSTED_PROXY_IPS
    settings.TRUSTED_PROXY_IPS = []
    request = SimpleNamespace(
        headers={"x-forwarded-for": "203.0.113.10"},
        client=SimpleNamespace(host="10.0.0.5"),
    )

    try:
        assert _client_ip(request) == "10.0.0.5"
    finally:
        settings.TRUSTED_PROXY_IPS = saved


def test_forwarded_for_is_used_for_trusted_proxy():
    saved = settings.TRUSTED_PROXY_IPS
    settings.TRUSTED_PROXY_IPS = ["10.0.0.5"]
    request = SimpleNamespace(
        headers={"x-forwarded-for": "203.0.113.10, 10.0.0.5"},
        client=SimpleNamespace(host="10.0.0.5"),
    )

    try:
        assert _client_ip(request) == "203.0.113.10"
    finally:
        settings.TRUSTED_PROXY_IPS = saved


def test_unix_socket_request_uses_the_nginx_real_ip_header():
    """In production there is no peer address, only nginx's own headers.

    Without this every guest hashed to the same "unknown" bucket and ten bad
    logins anywhere locked the whole site out.
    """

    request = SimpleNamespace(
        headers={"x-real-ip": "203.0.113.10"},
        client=None,
    )

    assert _client_ip(request) == "203.0.113.10"


def test_unix_socket_request_falls_back_to_the_forwarded_chain():
    saved = settings.TRUSTED_PROXY_IPS
    settings.TRUSTED_PROXY_IPS = ["10.0.0.5"]
    request = SimpleNamespace(
        headers={"x-forwarded-for": "203.0.113.10, 10.0.0.5"},
        client=None,
    )

    try:
        assert _client_ip(request) == "203.0.113.10"
    finally:
        settings.TRUSTED_PROXY_IPS = saved


def test_a_spoofed_forwarded_header_cannot_pick_the_bucket():
    """An untrusted TCP peer is its own identity, whatever it claims to be."""

    saved = settings.TRUSTED_PROXY_IPS
    settings.TRUSTED_PROXY_IPS = ["10.0.0.5"]
    request = SimpleNamespace(
        headers={"x-forwarded-for": "1.1.1.1", "x-real-ip": "2.2.2.2"},
        client=SimpleNamespace(host="198.51.100.7"),
    )

    try:
        assert _client_ip(request) == "198.51.100.7"
    finally:
        settings.TRUSTED_PROXY_IPS = saved


def test_localhost_proxy_is_trusted_by_default():
    """Behind nginx every request otherwise shares one rate-limit bucket."""

    config = _base_settings()

    assert "127.0.0.1" in config.TRUSTED_PROXY_IPS


def test_production_rejects_debug_and_weak_jwt_secret():
    with pytest.raises(ValidationError) as exc:
        _base_settings(
            ENVIRONMENT="production",
            DEBUG=True,
            JWT_SECRET_KEY="short",
        )

    message = str(exc.value)
    assert "DEBUG must be false in production" in message
    assert "JWT_SECRET_KEY must be at least 32 characters" in message


def test_production_requires_uzum_webhook_credentials():
    with pytest.raises(ValidationError) as exc:
        _production_settings(UZUM_SERVICE_ID=123123)

    assert "UZUM_MERCHANT_USERNAME and UZUM_MERCHANT_PASSWORD are required" in str(
        exc.value
    )


def test_production_requires_uzum_service_id_when_credentials_set():
    with pytest.raises(ValidationError) as exc:
        _production_settings(
            UZUM_MERCHANT_USERNAME="uzwellness",
            UZUM_MERCHANT_PASSWORD="secret",
        )

    assert "UZUM_SERVICE_ID is required" in str(exc.value)


def test_production_accepts_unconfigured_payment_providers():
    config = _production_settings()

    assert config.ENVIRONMENT == "production"


def test_production_rejects_the_log_email_backend():
    """Otherwise every confirmation and cancellation code is silently dropped."""

    with pytest.raises(ValidationError) as exc:
        _production_settings(EMAIL_BACKEND="log", RESEND_API_KEY=None)

    assert "EMAIL_BACKEND must be 'smtp' or 'resend'" in str(exc.value)


def test_production_rejects_wildcard_cors_origin():
    with pytest.raises(ValidationError) as exc:
        _production_settings(CORS_ORIGINS=["*"])

    assert "never '*'" in str(exc.value)


def test_production_rejects_plain_http_cors_origin():
    with pytest.raises(ValidationError) as exc:
        _production_settings(
            CORS_ORIGINS=["https://uzwellness.com", "http://localhost:3000"]
        )

    message = str(exc.value)
    assert "CORS_ORIGINS must be https in production" in message
    assert "http://localhost:3000" in message


def test_production_rejects_a_checkout_terminal_without_fiscal_codes():
    """Uzum answers 3045 mid-payment when auto-fiscalization has no tax data."""

    with pytest.raises(ValidationError) as exc:
        _production_settings(
            UZUM_CHECKOUT_TERMINAL_ID="term-1",
            UZUM_CHECKOUT_API_KEY="key-1",
        )

    message = str(exc.value)
    assert "UZUM_CHECKOUT_TIN" in message
    assert "auto-fiscalization" in message


def test_production_accepts_a_fully_configured_checkout_terminal():
    config = _production_settings(
        UZUM_CHECKOUT_TERMINAL_ID="term-1",
        UZUM_CHECKOUT_API_KEY="key-1",
        UZUM_CHECKOUT_TIN="300717633",
        UZUM_CHECKOUT_SPIC="10703999001000000",
        UZUM_CHECKOUT_PACKAGE_CODE="1495084",
    )

    assert config.uzum_checkout_enabled is True
