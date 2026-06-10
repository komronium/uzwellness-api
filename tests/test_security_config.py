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


def test_production_requires_enabled_payment_webhook_secrets():
    with pytest.raises(ValidationError) as exc:
        _base_settings(
            ENVIRONMENT="production",
            PAYME_MERCHANT_ID="payme-merchant",
            CLICK_SERVICE_ID="click-service",
        )

    message = str(exc.value)
    assert "PAYME_MERCHANT_KEY is required" in message
    assert "CLICK_SECRET_KEY is required" in message


def test_production_accepts_unconfigured_payment_providers():
    config = _base_settings(ENVIRONMENT="production")

    assert config.ENVIRONMENT == "production"
