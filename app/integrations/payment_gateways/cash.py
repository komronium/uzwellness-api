from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from app.integrations.payment_gateways.base import WebhookResult


class CashGateway:
    """Cash payments don't redirect or webhook — admin confirms manually."""

    code = "cash"

    def build_checkout_url(
        self,
        *,
        amount: Decimal,
        currency: str,
        merchant_trans_id: str,
    ) -> str | None:
        return None

    def verify_webhook(self, *, payload: dict, headers: Mapping[str, str]) -> bool:
        return False

    def parse_webhook(self, *, payload: dict) -> WebhookResult:
        raise NotImplementedError("Cash gateway has no webhook")
