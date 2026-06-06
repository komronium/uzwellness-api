import uuid

from fastapi import APIRouter, Depends

from app.api.deps import LocaleDep
from app.schemas.room_offer import RoomOfferSearchRequest, RoomOfferSearchResponse
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
    offers: RoomOfferService = Depends(get_room_offer_service),
) -> RoomOfferSearchResponse:
    return await offers.search(
        sanatorium_id=sanatorium_id,
        payload=payload,
        locale=locale,
    )
