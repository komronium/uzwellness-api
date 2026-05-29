from fastapi import APIRouter, Depends

from app.api.deps import LocaleDep
from app.core.pagination import Pagination
from app.schemas.sanatorium_featured import (
    FeaturedSanatoriumCard,
    FeaturedSanatoriumList,
)
from app.services.exchange_rate_service import (
    ExchangeRateService,
    get_exchange_rate_service,
)
from app.services.sanatorium_query_service import (
    SanatoriumQueryService,
    get_sanatorium_query_service,
)

router = APIRouter(prefix="/sanatoriums", tags=["Sanatoriums"])


@router.get("/featured", response_model=FeaturedSanatoriumList)
async def list_featured_sanatoriums(
    locale: LocaleDep,
    page: Pagination,
    sanatoriums: SanatoriumQueryService = Depends(get_sanatorium_query_service),
    rates: ExchangeRateService = Depends(get_exchange_rate_service),
) -> FeaturedSanatoriumList:
    rate = await rates.get_usd_uzs()
    rows, total = await sanatoriums.list_featured(
        limit=page.limit,
        offset=page.offset,
        usd_uzs_rate=rate.rate if rate else None,
    )
    return FeaturedSanatoriumList(
        items=[
            FeaturedSanatoriumCard.from_obj(
                sanatorium,
                locale=locale,
                min_price=min_price,
                min_price_currency=min_price_currency,
                min_price_usd=min_price_usd,
            )
            for sanatorium, min_price, min_price_currency, min_price_usd in rows
        ],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )
