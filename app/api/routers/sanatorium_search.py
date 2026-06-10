import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import LocaleDep
from app.core.pagination import Pagination
from app.models.sanatorium import PropertyType
from app.schemas.search import StaySearchList
from app.services.search_service import SearchService, get_search_service

router = APIRouter(prefix="/sanatoriums", tags=["Sanatoriums"])


@router.get("/search", response_model=StaySearchList)
async def search_sanatorium_stays(
    locale: LocaleDep,
    page: Pagination,
    search: SearchService = Depends(get_search_service),
    check_in: date = Query(...),
    check_out: date = Query(...),
    adults: int = Query(default=2, ge=1),
    children: int = Query(default=0, ge=0),
    location: str | None = Query(default=None, max_length=200),
    sanatorium_id: uuid.UUID | None = Query(default=None),
    destination_id: uuid.UUID | None = Query(default=None),
    treatment_focus: str | None = Query(default=None, max_length=60),
    property_type: PropertyType | None = Query(default=None),
) -> StaySearchList:
    if check_out <= check_in:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="check_out must be after check_in",
        )
    items, total = await search.search_stays(
        locale=locale,
        check_in=check_in,
        check_out=check_out,
        adults=adults,
        children=children,
        location=location,
        sanatorium_id=sanatorium_id,
        destination_id=destination_id,
        treatment_focus=treatment_focus or None,
        property_type=property_type,
        limit=page.limit,
        offset=page.offset,
    )
    return StaySearchList(
        items=items, total=total, limit=page.limit, offset=page.offset
    )
