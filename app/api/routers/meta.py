from fastapi import APIRouter

from app.core.meta import META, Option

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("")
async def get_meta() -> dict[str, list[Option]]:
    """Selectable option catalogs (value + uz/ru/en label) for every dropdown."""
    return META
