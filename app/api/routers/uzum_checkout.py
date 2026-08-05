"""Uzum Checkout merchant callbacks.

Three URLs, fixed on Uzum's terminal at onboarding and therefore effectively
permanent:

    POST /payments/uzum-checkout/callback   financial operation result
    POST /payments/uzum-checkout/event      business event (FORM_CLOSED)
    POST /payments/uzum-checkout/receipt    fiscal receipt generated

Every one answers ``200 {}``; without that acknowledgement Uzum redelivers up
to five times. They are receive-only for now — see ``uzum_checkout_service``
for why nothing is applied to a booking here.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Request

from app.services.uzum_checkout_service import (
    UzumCheckoutService,
    client_ip,
    get_uzum_checkout_service,
)

router = APIRouter(prefix="/payments/uzum-checkout", tags=["Payments"])

logger = logging.getLogger("uzwellness.uzum_checkout")

# Uzum expects an empty JSON object as the acknowledgement.
_ACK: dict[str, Any] = {}

_DOC_RESPONSES = {
    200: {
        "description": "Acknowledged. Any other status makes Uzum redeliver.",
        "content": {"application/json": {"example": {}}},
    }
}


async def _payload(request: Request) -> dict:
    """Parse the body, keeping malformed input rather than rejecting it.

    A body we cannot parse will not parse on redelivery either, so it is
    recorded verbatim and acknowledged instead of triggering five retries.
    """
    raw = await request.body()
    try:
        parsed = json.loads(raw)
    except ValueError:
        logger.warning("Checkout callback body is not JSON: %r", raw[:500])
        return {"_unparsed": raw.decode("utf-8", "replace")[:4000]}
    if not isinstance(parsed, dict):
        logger.warning("Checkout callback body is not an object: %r", raw[:500])
        return {"_unparsed": parsed}
    return parsed


@router.post("/callback", responses=_DOC_RESPONSES)
async def acquiring_callback(
    request: Request,
    checkout: UzumCheckoutService = Depends(get_uzum_checkout_service),
) -> dict:
    """`callback_url` — AUTHORIZE / COMPLETE / REFUND / REVERSE result."""
    await checkout.record_acquiring(
        await _payload(request), source_ip=client_ip(request)
    )
    return _ACK


@router.post("/event", responses=_DOC_RESPONSES)
async def business_event_callback(
    request: Request,
    checkout: UzumCheckoutService = Depends(get_uzum_checkout_service),
) -> dict:
    """`event_callback_url` — business events such as `FORM_CLOSED`."""
    await checkout.record_event(await _payload(request), source_ip=client_ip(request))
    return _ACK


@router.post("/receipt", responses=_DOC_RESPONSES)
async def receipt_callback(
    request: Request,
    checkout: UzumCheckoutService = Depends(get_uzum_checkout_service),
) -> dict:
    """`receipt_callback_url` — a fiscal receipt is ready."""
    await checkout.record_receipt(await _payload(request), source_ip=client_ip(request))
    return _ACK
