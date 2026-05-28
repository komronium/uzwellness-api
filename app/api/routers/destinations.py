import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile, status

from app.api.deps import (
    IncludeTranslationsDep,
    LocaleDep,
    OptionalUser,
    not_found,
    require_roles,
)
from app.core.pagination import LargePagination
from app.core.storage import StorageBackend, detect_image_mime, get_storage
from app.core.uploads import read_upload
from app.models.user import UserRole
from app.schemas.destination import (
    DestinationAdminList,
    DestinationAdminRead,
    DestinationCreate,
    DestinationList,
    DestinationRead,
    DestinationTileList,
    DestinationTileRead,
    DestinationUpdate,
)
from app.services.destination_service import (
    DestinationService,
    get_destination_service,
)
from app.services.exchange_rate_service import (
    ExchangeRateService,
    get_exchange_rate_service,
)

router = APIRouter(prefix="/destinations", tags=["destinations"])

require_super_admin = require_roles(UserRole.SUPER_ADMIN)


@router.get("", response_model=DestinationList | DestinationAdminList)
async def list_destinations(
    locale: LocaleDep,
    include_translations: IncludeTranslationsDep,
    page: LargePagination,
    current_user: OptionalUser,
    active_only: bool = Query(default=True),
    destinations: DestinationService = Depends(get_destination_service),
) -> DestinationList | DestinationAdminList:
    if current_user is None or current_user.role != UserRole.SUPER_ADMIN:
        active_only = True
    items, total = await destinations.list_all(
        limit=page.limit, offset=page.offset, active_only=active_only
    )
    if include_translations:
        return DestinationAdminList(
            items=[DestinationAdminRead.model_validate(d) for d in items],
            total=total,
            limit=page.limit,
            offset=page.offset,
        )
    return DestinationList(
        items=[DestinationRead.from_obj(d, locale) for d in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/tiles", response_model=DestinationTileList)
async def list_destination_tiles(
    locale: LocaleDep,
    destinations: DestinationService = Depends(get_destination_service),
    rates: ExchangeRateService = Depends(get_exchange_rate_service),
) -> DestinationTileList:
    """Homepage feed: active destinations with sanatorium count + min price.

    `min_price_usd` is normalized using the USD/UZS exchange rate. Rooms in
    other currencies (none today, but future-proofed) drop out of the min.
    A destination with no approved sanatoriums returns count=0, price=null.
    """
    rate = await rates.get_usd_uzs()
    rows = await destinations.list_tiles(
        usd_uzs_rate=rate.rate if rate else None
    )
    tiles = [
        DestinationTileRead.from_aggregate(
            destination,
            locale,
            sanatoriums_count=count,
            min_price_usd=price,
        )
        for destination, count, price in rows
    ]
    return DestinationTileList(items=tiles, total=len(tiles))


@router.get("/{slug_or_id}", response_model=DestinationRead | DestinationAdminRead)
async def get_destination(
    slug_or_id: str,
    locale: LocaleDep,
    include_translations: IncludeTranslationsDep,
    current_user: OptionalUser,
    destinations: DestinationService = Depends(get_destination_service),
) -> DestinationRead | DestinationAdminRead:
    destination = None
    try:
        dest_uuid = uuid.UUID(slug_or_id)
    except ValueError:
        destination = await destinations.get_by_slug(slug_or_id)
    else:
        destination = await destinations.get_by_id(dest_uuid)
    can_view_inactive = (
        current_user is not None and current_user.role == UserRole.SUPER_ADMIN
    )
    if destination is None or (not destination.is_active and not can_view_inactive):
        raise not_found("Destination not found")
    if include_translations:
        return DestinationAdminRead.model_validate(destination)
    return DestinationRead.from_obj(destination, locale)


@router.post(
    "",
    response_model=DestinationAdminRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_super_admin)],
)
async def create_destination(
    payload: DestinationCreate,
    destinations: DestinationService = Depends(get_destination_service),
) -> DestinationAdminRead:
    return DestinationAdminRead.model_validate(
        await destinations.create(payload)
    )


@router.post(
    "/{destination_id}/hero-image",
    response_model=DestinationAdminRead,
    dependencies=[Depends(require_super_admin)],
)
async def upload_hero_image(
    destination_id: uuid.UUID,
    file: UploadFile = File(...),
    destinations: DestinationService = Depends(get_destination_service),
    storage: StorageBackend = Depends(get_storage),
) -> DestinationAdminRead:
    destination = await destinations.get_by_id(destination_id)
    if destination is None:
        raise not_found("Destination not found")
    content, mime = await read_upload(
        file, detect_mime=detect_image_mime, allowed_label="JPEG, PNG, WebP"
    )
    updated = await destinations.update_hero_image(
        destination,
        content=content,
        content_type=mime,
        storage=storage,
    )
    return DestinationAdminRead.model_validate(updated)


@router.patch(
    "/{destination_id}",
    response_model=DestinationAdminRead,
    dependencies=[Depends(require_super_admin)],
)
async def update_destination(
    destination_id: uuid.UUID,
    payload: DestinationUpdate,
    destinations: DestinationService = Depends(get_destination_service),
) -> DestinationAdminRead:
    destination = await destinations.get_by_id(destination_id)
    if destination is None:
        raise not_found("Destination not found")
    return DestinationAdminRead.model_validate(
        await destinations.update(destination, payload)
    )


@router.delete(
    "/{destination_id}/hero-image",
    response_model=DestinationAdminRead,
    dependencies=[Depends(require_super_admin)],
)
async def delete_hero_image(
    destination_id: uuid.UUID,
    destinations: DestinationService = Depends(get_destination_service),
    storage: StorageBackend = Depends(get_storage),
) -> DestinationAdminRead:
    destination = await destinations.get_by_id(destination_id)
    if destination is None:
        raise not_found("Destination not found")
    updated = await destinations.delete_hero_image(destination, storage)
    return DestinationAdminRead.model_validate(updated)


@router.delete(
    "/{destination_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_super_admin)],
)
async def delete_destination(
    destination_id: uuid.UUID,
    destinations: DestinationService = Depends(get_destination_service),
) -> None:
    destination = await destinations.get_by_id(destination_id)
    if destination is None:
        raise not_found("Destination not found")
    await destinations.delete(destination)
