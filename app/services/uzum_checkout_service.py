"""Recording side of the Uzum Checkout callbacks.

Deliberately does nothing but persist. Checkout callbacks carry no signature,
so their contents cannot be trusted; the state of an order is settled by
calling Uzum's ``/api/v1/payment/getOrderStatus`` back, which needs the
terminal credentials we do not have yet. Until that lands, every callback is
stored unprocessed and acknowledged so Uzum stops retrying.
"""

from __future__ import annotations

import logging

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.uzum_checkout_event import UzumCheckoutCallbackKind, UzumCheckoutEvent
from app.schemas.uzum_checkout import (
    AcquiringCallback,
    BusinessEventCallback,
    ReceiptCallback,
)

logger = logging.getLogger("uzwellness.uzum_checkout")


def client_ip(request: Request) -> str | None:
    """Best-effort source address, for observability and the nginx allowlist.

    Behind nginx the socket peer is always local, so the forwarded header is
    the only useful signal. It is spoofable and therefore recorded, never
    trusted for authorization — that belongs in nginx, above this process.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host[:64] if request.client else None


class UzumCheckoutService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def record_acquiring(
        self, payload: dict, *, source_ip: str | None
    ) -> UzumCheckoutEvent:
        parsed = AcquiringCallback.model_validate(payload)
        logger.info(
            "Checkout acquiring callback: order=%s number=%s %s/%s from %s",
            parsed.order_id,
            parsed.order_number,
            parsed.operation_type,
            parsed.operation_state,
            source_ip,
        )
        return await self._store(
            UzumCheckoutEvent(
                kind=UzumCheckoutCallbackKind.ACQUIRING,
                order_id=parsed.order_id,
                order_number=parsed.order_number,
                operation_type=parsed.operation_type,
                operation_state=parsed.operation_state,
                rrn=parsed.rrn,
                source_ip=source_ip,
                payload=payload,
            )
        )

    async def record_event(
        self, payload: dict, *, source_ip: str | None
    ) -> UzumCheckoutEvent:
        parsed = BusinessEventCallback.model_validate(payload)
        logger.info(
            "Checkout business event: order=%s number=%s %s from %s",
            parsed.order_id,
            parsed.order_number,
            parsed.event_type,
            source_ip,
        )
        return await self._store(
            UzumCheckoutEvent(
                kind=UzumCheckoutCallbackKind.EVENT,
                order_id=parsed.order_id,
                order_number=parsed.order_number,
                event_type=parsed.event_type,
                source_ip=source_ip,
                payload=payload,
            )
        )

    async def record_receipt(
        self, payload: dict, *, source_ip: str | None
    ) -> UzumCheckoutEvent:
        parsed = ReceiptCallback.model_validate(payload)
        logger.info(
            "Checkout receipt callback: order=%s %s from %s",
            parsed.order_id,
            parsed.receipt_type,
            source_ip,
        )
        return await self._store(
            UzumCheckoutEvent(
                kind=UzumCheckoutCallbackKind.RECEIPT,
                order_id=parsed.order_id,
                receipt_type=parsed.receipt_type,
                receipt_url=parsed.receipt_url,
                source_ip=source_ip,
                payload=payload,
            )
        )

    async def _store(self, event: UzumCheckoutEvent) -> UzumCheckoutEvent:
        self.db.add(event)
        await self.db.commit()
        await self.db.refresh(event)
        return event


def get_uzum_checkout_service(
    db: AsyncSession = Depends(get_db),
) -> UzumCheckoutService:
    return UzumCheckoutService(db)
