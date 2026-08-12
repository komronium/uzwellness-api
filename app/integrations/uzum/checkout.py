"""HTTP client for the Uzum Checkout API (spec 1.10.3).

Checkout is the *outbound* half of our Uzum integration: the guest pays with a
card on our site, so we call Uzum to register an order and then send the guest
to the payment page it returns. (The Merchant API in ``uzum_service`` is the
opposite direction — Uzum calls us.)

Every method answers with the same envelope::

    {"errorCode": 0, "message": "...", "result": {...}}

``errorCode`` is the real status: HTTP is 200 even for failures, so a non-zero
code is turned into :class:`UzumCheckoutApiError` here and never leaks upwards
as a "successful" empty result.

Auth is two headers, issued by Uzum per environment: ``X-Terminal-Id`` and
``X-API-Key``.

Docs: https://developer.uzumbank.uz/en/checkout/
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger("uzwellness.uzum_checkout")

REGISTER_PATH = "/api/v1/payment/register"
ORDER_STATUS_PATH = "/api/v1/payment/getOrderStatus"
REFUND_PATH = "/api/v1/acquiring/refund"

# Locales Uzum accepts for the payment form, keyed by our own locale codes.
_FORM_LOCALES = {"uz": "uz-UZ", "ru": "ru-RU", "en": "en-EN"}
DEFAULT_FORM_LOCALE = "ru-RU"

# Uzum's own state names for a registered order.
ORDER_REGISTERED = "REGISTERED"
ORDER_COMPLETED = "COMPLETED"
ORDER_DECLINED = "DECLINED"
ORDER_REFUNDED = "REFUNDED"

# The register/getOrderStatus results are documented only as "result: {...}",
# so the id and the URL are read from a list of candidates. The live sandbox
# answers with `paymentRedirectUrl`; the rest are names Uzum's own examples and
# SDKs use, kept so a renamed field cannot break checkout silently.
_ORDER_ID_KEYS = ("orderId", "id", "paymentId")
_PAYMENT_URL_KEYS = (
    "paymentRedirectUrl",
    "paymentUrl",
    "checkoutUrl",
    "redirectUrl",
    "formUrl",
    "url",
)
_STATUS_KEYS = ("status", "orderStatus", "paymentStatus", "state")


def form_locale(locale: str | None) -> str:
    return _FORM_LOCALES.get((locale or "").lower(), DEFAULT_FORM_LOCALE)


class UzumCheckoutApiError(Exception):
    """Uzum refused the call — either a non-zero ``errorCode`` or a transport
    failure (``code`` is then ``None``)."""

    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(f"{code}: {message}" if code is not None else message)
        self.code = code
        self.message = message


class UzumCheckoutClient:
    def __init__(
        self,
        *,
        base_url: str,
        terminal_id: str,
        api_key: str,
        timeout: float = 20.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.terminal_id = terminal_id
        self.api_key = api_key
        self.timeout = timeout

    @classmethod
    def from_settings(cls) -> "UzumCheckoutClient":
        return cls(
            base_url=settings.UZUM_CHECKOUT_API_URL,
            terminal_id=settings.UZUM_CHECKOUT_TERMINAL_ID,
            api_key=settings.UZUM_CHECKOUT_API_KEY,
            timeout=settings.UZUM_CHECKOUT_TIMEOUT_SECONDS,
        )

    async def register(
        self,
        *,
        amount_tiyin: int,
        client_id: str,
        order_number: str,
        payment_details: str,
        locale: str | None = None,
        cart: dict[str, Any] | None = None,
        success_url: str | None = None,
        failure_url: str | None = None,
        view_type: str = "REDIRECT",
    ) -> dict[str, Any]:
        """Register a one-step card payment; returns Uzum's ``result`` block."""

        # Uzum validates both redirect URLs as https — an http one is rejected
        # with 2000 before the order is ever created.
        body: dict[str, Any] = {
            "amount": amount_tiyin,
            "clientId": client_id,
            "currency": 860,  # ISO 4217 — Checkout only settles in UZS.
            "paymentDetails": payment_details[:1024],
            "orderNumber": order_number,
            "successUrl": success_url or settings.UZUM_CHECKOUT_SUCCESS_URL,
            "failureUrl": failure_url or settings.UZUM_CHECKOUT_FAILURE_URL,
            "viewType": view_type,
            "paymentParams": {"operationType": "PAYMENT", "payType": "ONE_STEP"},
            "sessionTimeoutSecs": settings.UZUM_CHECKOUT_SESSION_TIMEOUT_SECS,
        }
        if cart is not None:
            body["merchantParams"] = {"cart": cart}
        return await self._post(
            REGISTER_PATH,
            body,
            headers={"Content-Language": form_locale(locale)},
        )

    async def get_order_status(self, order_id: str) -> dict[str, Any]:
        return await self._post(ORDER_STATUS_PATH, {"orderId": order_id})

    async def refund(
        self,
        *,
        order_id: str,
        amount_tiyin: int,
        operation_id: str | None = None,
        cart: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Full or partial refund of a COMPLETED order.

        ``X-Operation-Id`` is Uzum's idempotency key: passing the same value
        twice can never refund twice, so callers that may retry should supply
        their own stable id instead of the generated one.
        """

        body: dict[str, Any] = {"orderId": order_id, "amount": amount_tiyin}
        if cart is not None:
            body["cart"] = cart
        return await self._post(
            REFUND_PATH,
            body,
            headers={"X-Operation-Id": operation_id or str(uuid.uuid4())},
        )

    async def _post(
        self,
        path: str,
        body: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if not (self.terminal_id and self.api_key):
            raise UzumCheckoutApiError("Uzum Checkout credentials are not configured")

        request_headers = {
            "X-Terminal-Id": self.terminal_id,
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
            **(headers or {}),
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}{path}", json=body, headers=request_headers
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as exc:
            logger.warning("Uzum Checkout %s failed: %s", path, exc)
            raise UzumCheckoutApiError(f"Uzum Checkout is unreachable: {exc}") from exc
        except ValueError as exc:
            logger.warning("Uzum Checkout %s returned non-JSON body", path)
            raise UzumCheckoutApiError(
                "Uzum Checkout returned a non-JSON body"
            ) from exc

        if not isinstance(payload, dict):
            raise UzumCheckoutApiError("Uzum Checkout returned an unexpected body")

        error_code = payload.get("errorCode")
        if error_code:
            message = str(payload.get("message") or "")
            logger.warning("Uzum Checkout %s → %s %s", path, error_code, message[:500])
            raise UzumCheckoutApiError(message, code=_as_int(error_code))

        result = payload.get("result")
        return result if isinstance(result, dict) else {}


def pick_order_id(result: dict[str, Any]) -> str | None:
    return _first_str(result, _ORDER_ID_KEYS)


def pick_payment_url(result: dict[str, Any]) -> str | None:
    return _first_str(result, _PAYMENT_URL_KEYS)


def pick_status(result: dict[str, Any]) -> str | None:
    status = _first_str(result, _STATUS_KEYS)
    return status.upper() if status else None


def _first_str(result: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    """First non-empty string under ``keys``, looking one level into objects.

    Uzum documents the result blocks only as ``{...}``, so a nested shape such
    as ``{"order": {"orderId": ...}}`` is tolerated rather than guessed at.
    """

    for key in keys:
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for value in result.values():
        if isinstance(value, dict):
            nested = _first_str(value, keys)
            if nested is not None:
                return nested
    return None


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
