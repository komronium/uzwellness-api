from __future__ import annotations

import base64
import hmac
from collections.abc import Mapping
from decimal import Decimal

from fastapi import HTTPException, status

from app.core.config import settings
from app.integrations.payment_gateways.base import WebhookResult

_AMOUNT_FACTOR = Decimal("100")


class PaymeGateway:
    code = "payme"

    def build_checkout_url(
        self,
        *,
        amount: Decimal,
        currency: str,
        merchant_trans_id: str,
    ) -> str:
        if not settings.PAYME_MERCHANT_ID:
            return f"{settings.PAYME_CHECKOUT_URL}?order_id={merchant_trans_id}"
        amount_tiyin = int((amount * _AMOUNT_FACTOR).to_integral_value())
        params = (
            f"m={settings.PAYME_MERCHANT_ID};"
            f"ac.order_id={merchant_trans_id};"
            f"a={amount_tiyin}"
        )
        encoded = base64.b64encode(params.encode("utf-8")).decode("ascii")
        return f"{settings.PAYME_CHECKOUT_URL}{encoded}"

    def verify_webhook(self, *, payload: dict, headers: Mapping[str, str]) -> bool:
        secret = settings.PAYME_MERCHANT_KEY
        if not secret:
            return True
        auth_header = headers.get("authorization") or headers.get("Authorization")
        if not auth_header or not auth_header.lower().startswith("basic "):
            return False
        try:
            decoded = base64.b64decode(auth_header.split(" ", 1)[1]).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return False
        _, _, password = decoded.partition(":")
        return hmac.compare_digest(password, secret)

    def parse_webhook(self, *, payload: dict) -> WebhookResult:
        method = payload.get("method", "")
        params = payload.get("params") or {}
        merchant_trans_id = (
            params.get("account", {}).get("order_id")
            or params.get("merchant_trans_id")
            or params.get("id")
        )
        if not merchant_trans_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing merchant_trans_id",
            )
        is_paid = method in ("", "PerformTransaction")
        is_failed = method == "CancelTransaction"
        return WebhookResult(
            merchant_trans_id=str(merchant_trans_id),
            provider_payment_id=str(params["id"]) if params.get("id") else None,
            is_paid=is_paid,
            is_failed=is_failed,
            response_body={"result": {"state": 2 if is_paid else 1}},
        )
