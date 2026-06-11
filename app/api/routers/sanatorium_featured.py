from fastapi import APIRouter, Depends

from app.api.deps import ConverterDep, LocaleDep
from app.core.pagination import Pagination
from app.schemas.sanatorium_featured import (
    FeaturedSanatoriumCard,
    FeaturedSanatoriumList,
)
from app.services.sanatorium_query_service import (
    SanatoriumQueryService,
    get_sanatorium_query_service,
)

router = APIRouter(prefix="/sanatoriums", tags=["Sanatoriums"])


@router.get("/featured", response_model=FeaturedSanatoriumList)
async def list_featured_sanatoriums(
    locale: LocaleDep,
    converter: ConverterDep,
    page: Pagination,
    sanatoriums: SanatoriumQueryService = Depends(get_sanatorium_query_service),
) -> FeaturedSanatoriumList:
    rows, total = await sanatoriums.list_featured(
        limit=page.limit,
        offset=page.offset,
        rates_to_uzs=converter.rates_to_uzs,
    )
    return FeaturedSanatoriumList(
        items=[
            FeaturedSanatoriumCard.from_obj(
                sanatorium,
                locale=locale,
                min_price=min_price,
                min_price_currency=min_price_currency,
                min_price_usd=min_price_usd,
                min_price_display=converter.convert(min_price, min_price_currency)
                if min_price is not None and min_price_currency is not None
                else None,
                display_currency=converter.target,
            )
            for sanatorium, min_price, min_price_currency, min_price_usd in rows
        ],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )
