from fastapi import APIRouter, Depends

from app.api.deps import public_cache
from app.core.meta import META, Option

router = APIRouter(prefix="/meta", tags=["System"])


@router.get("", dependencies=[Depends(public_cache)])
async def get_meta() -> dict[str, list[Option]]:
    """Selectable option catalogs (value + uz/ru/en label) for every dropdown."""
    return META
