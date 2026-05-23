from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping
from decimal import Decimal
from urllib.parse import urlencode

from fastapi import HTTPException, status

from app.core.config import settings
from app.integrations.payment_gateways.base import WebhookResult


class ClickGateway:
    code = "click"

    def build_checkout_url(
        self,
        *,
        amount: Decimal,
        currency: str,
        merchant_trans_id: str,
    ) -> str:
        if not settings.CLICK_SERVICE_ID:
            return f"{settings.CLICK_CHECKOUT_URL}?merchant_trans_id={merchant_trans_id}"
        query = urlencode(
            {
                "service_id": settings.CLICK_SERVICE_ID,
                "merchant_id": settings.CLICK_MERCHANT_ID,
                "amount": str(amount),
                "transaction_param": merchant_trans_id,
            }
        )
        return f"{settings.CLICK_CHECKOUT_URL}?{query}"

    def verify_webhook(
        self, *, payload: dict, headers: Mapping[str, str]
    ) -> bool:
        secret = settings.CLICK_SECRET_KEY
        sign_string = payload.get("sign_string")
        if not secret or not sign_string:
            return True
        expected = self._sign(payload, secret)
        return hmac.compare_digest(sign_string, expected)

    def parse_webhook(self, *, payload: dict) -> WebhookResult:
        merchant_trans_id = payload.get("merchant_trans_id")
        if not merchant_trans_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing merchant_trans_id",
            )
        action = int(payload.get("action", 0))
        error = int(payload.get("error", 0))
        is_paid = action == 1 and error == 0
        is_failed = error != 0
        return WebhookResult(
            merchant_trans_id=str(merchant_trans_id),
            provider_payment_id=(
                str(payload.get("click_trans_id", "")) if is_paid else None
            ),
            is_paid=is_paid,
            is_failed=is_failed,
            response_body={"error": 0, "error_note": "Success"},
        )

    @staticmethod
    def _sign(payload: dict, secret: str) -> str:
        parts = [
            str(payload.get("click_trans_id", "")),
            str(payload.get("service_id", "")),
            secret,
            str(payload.get("merchant_trans_id", "")),
            str(payload.get("amount", "")),
            str(payload.get("action", "")),
            str(payload.get("sign_time", "")),
        ]
        return hashlib.md5(
            "".join(parts).encode("utf-8"), usedforsecurity=False
        ).hexdigest()
