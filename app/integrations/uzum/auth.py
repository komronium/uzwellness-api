"""HTTP Basic authentication for the Uzum Bank Merchant API webhooks.

Uzum sends ``Authorization: Basic base64(username:password)`` on every
webhook. Credentials are agreed out of band and live in the environment; when
they are not configured every request is rejected, so an unconfigured
deployment can never be driven by a spoofed webhook.
"""

from __future__ import annotations

import base64
import binascii
import hmac
from collections.abc import Mapping

from app.core.config import settings
from app.integrations.uzum.errors import UzumError, UzumErrorCode


def verify_basic_auth(headers: Mapping[str, str]) -> None:
    """Raise ``UzumError(ACCESS_DENIED)`` unless the header matches settings."""

    expected_user = settings.UZUM_MERCHANT_USERNAME
    expected_password = settings.UZUM_MERCHANT_PASSWORD
    if not expected_user or not expected_password:
        raise UzumError(
            UzumErrorCode.ACCESS_DENIED, "Uzum merchant credentials are not configured"
        )

    header = headers.get("authorization") or headers.get("Authorization")
    if not header:
        raise UzumError(UzumErrorCode.ACCESS_DENIED, "Missing Authorization header")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "basic" or not token:
        raise UzumError(UzumErrorCode.ACCESS_DENIED, "Authorization must use Basic")
    try:
        decoded = base64.b64decode(token.strip(), validate=True).decode("utf-8")
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise UzumError(
            UzumErrorCode.ACCESS_DENIED, "Malformed Basic credentials"
        ) from exc

    username, separator, password = decoded.partition(":")
    if not separator:
        raise UzumError(UzumErrorCode.ACCESS_DENIED, "Malformed Basic credentials")

    # Compare both halves without short-circuiting on the first mismatch.
    user_ok = hmac.compare_digest(username, expected_user)
    password_ok = hmac.compare_digest(password, expected_password)
    if not (user_ok and password_ok):
        raise UzumError(UzumErrorCode.ACCESS_DENIED, "Invalid credentials")


def verify_service_id(service_id: int) -> None:
    """Reject webhooks addressed to a service id we do not serve."""

    if not settings.UZUM_SERVICE_ID:
        raise UzumError(
            UzumErrorCode.INVALID_SERVICE_ID, "UZUM_SERVICE_ID is not configured"
        )
    if service_id != settings.UZUM_SERVICE_ID:
        raise UzumError(
            UzumErrorCode.INVALID_SERVICE_ID, f"Unknown serviceId {service_id}"
        )
