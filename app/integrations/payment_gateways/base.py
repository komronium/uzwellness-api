from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol


@dataclass(slots=True)
class WebhookResult:
    """What a gateway extracts from a verified webhook payload."""

    merchant_trans_id: str
    provider_payment_id: str | None
    is_paid: bool
    is_failed: bool
    amount: Decimal | None = None
    response_body: dict = field(default_factory=dict)


class PaymentGateway(Protocol):
    """Each provider implements this interface; PaymentService stays provider-agnostic."""

    code: str

    def build_checkout_url(
        self,
        *,
        amount: Decimal,
        currency: str,
        merchant_trans_id: str,
    ) -> str | None: ...

    def verify_webhook(self, *, payload: dict, headers: Mapping[str, str]) -> bool: ...

    def parse_webhook(self, *, payload: dict) -> WebhookResult: ...
