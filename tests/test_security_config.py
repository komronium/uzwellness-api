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


def test_production_requires_uzum_webhook_credentials():
    with pytest.raises(ValidationError) as exc:
        _base_settings(ENVIRONMENT="production", UZUM_SERVICE_ID=123123)

    assert "UZUM_MERCHANT_USERNAME and UZUM_MERCHANT_PASSWORD are required" in str(
        exc.value
    )


def test_production_requires_uzum_service_id_when_credentials_set():
    with pytest.raises(ValidationError) as exc:
        _base_settings(
            ENVIRONMENT="production",
            UZUM_MERCHANT_USERNAME="uzwellness",
            UZUM_MERCHANT_PASSWORD="secret",
        )

    assert "UZUM_SERVICE_ID is required" in str(exc.value)


def test_production_accepts_unconfigured_payment_providers():
    config = _base_settings(ENVIRONMENT="production")

    assert config.ENVIRONMENT == "production"
