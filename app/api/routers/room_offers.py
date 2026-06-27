import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrencyDep, LocaleDep, OptionalUser
from app.core.database import get_db
from app.models.sanatorium import Sanatorium
from app.schemas.room_offer import RoomOfferSearchRequest, RoomOfferSearchResponse
from app.services.booking_pricing_policy import (
    BookingPricingPolicy,
    get_booking_pricing_policy,
)
from app.services.room_offer_service import (
    RoomOfferService,
    get_room_offer_service,
)

router = APIRouter(prefix="/sanatoriums", tags=["Sanatoriums"])


@router.post(
    "/{sanatorium_id}/room-offers/search", response_model=RoomOfferSearchResponse
)
async def search_sanatorium_room_offers(
    sanatorium_id: uuid.UUID,
    payload: RoomOfferSearchRequest,
    locale: LocaleDep,
    currency: CurrencyDep,
    current_user: OptionalUser,
    offers: RoomOfferService = Depends(get_room_offer_service),
    pricing: BookingPricingPolicy = Depends(get_booking_pricing_policy),
    db: AsyncSession = Depends(get_db),
) -> RoomOfferSearchResponse:
    # Agents see their B2B tier price; customers/anonymous see retail.
    sanatorium = await db.get(Sanatorium, sanatorium_id)
    agent_discount_percent = await pricing.agent_discount_for(current_user, sanatorium)
    return await offers.search(
        sanatorium_id=sanatorium_id,
        payload=payload,
        locale=locale,
        display_currency=currency,
        agent_discount_percent=agent_discount_percent,
    )
