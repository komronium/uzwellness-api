import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import IncludeTranslationsDep, LocaleDep, require_roles
from app.models.user import UserRole
from app.schemas.package import (
    PackageAdminList,
    PackageAdminRead,
    PackageCreate,
    PackageItemAdminRead,
    PackageItemCreate,
    PackageItemUpdate,
    PackageList,
    PackageRead,
    PackageUpdate,
)
from app.services.package_service import PackageService, get_package_service

router = APIRouter(prefix="/packages", tags=["packages"])

require_super_admin = require_roles(UserRole.SUPER_ADMIN)


@router.get("", response_model=None)
async def list_packages(
    locale: LocaleDep,
    include_translations: IncludeTranslationsDep,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    active_only: bool = Query(default=True),
    sanatorium_id: uuid.UUID | None = Query(default=None),
    duration_min: int | None = Query(default=None, ge=1),
    duration_max: int | None = Query(default=None, ge=1),
    price_min: Decimal | None = Query(default=None, ge=0),
    price_max: Decimal | None = Query(default=None, ge=0),
    packages: PackageService = Depends(get_package_service),
) -> PackageList | PackageAdminList:
    items, total = await packages.list_packages(
        limit=limit,
        offset=offset,
        active_only=active_only,
        sanatorium_id=sanatorium_id,
        duration_min=duration_min,
        duration_max=duration_max,
        price_min=price_min,
        price_max=price_max,
    )
    if include_translations:
        return PackageAdminList(
            items=[PackageAdminRead.model_validate(p) for p in items],
            total=total,
            limit=limit,
            offset=offset,
        )
    return PackageList(
        items=[PackageRead.from_obj(p, locale) for p in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{package_id_or_slug}", response_model=None)
async def get_package(
    package_id_or_slug: str,
    locale: LocaleDep,
    include_translations: IncludeTranslationsDep,
    packages: PackageService = Depends(get_package_service),
) -> PackageRead | PackageAdminRead:
    package = None
    try:
        package_uuid = uuid.UUID(package_id_or_slug)
    except ValueError:
        package_uuid = None
    if package_uuid is not None:
        package = await packages.get_by_id(package_uuid)
    if package is None:
        package = await packages.get_by_slug(package_id_or_slug)
    if package is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Package not found"
        )
    if include_translations:
        return PackageAdminRead.model_validate(package)
    return PackageRead.from_obj(package, locale)


@router.post(
    "",
    response_model=PackageAdminRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_super_admin)],
)
async def create_package(
    payload: PackageCreate,
    packages: PackageService = Depends(get_package_service),
) -> PackageAdminRead:
    return PackageAdminRead.model_validate(await packages.create(payload))


@router.patch(
    "/{package_id}",
    response_model=PackageAdminRead,
    dependencies=[Depends(require_super_admin)],
)
async def update_package(
    package_id: uuid.UUID,
    payload: PackageUpdate,
    packages: PackageService = Depends(get_package_service),
) -> PackageAdminRead:
    package = await packages.get_by_id(package_id)
    if package is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Package not found"
        )
    return PackageAdminRead.model_validate(await packages.update(package, payload))


@router.delete(
    "/{package_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_super_admin)],
)
async def delete_package(
    package_id: uuid.UUID,
    packages: PackageService = Depends(get_package_service),
) -> None:
    package = await packages.get_by_id(package_id)
    if package is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Package not found"
        )
    await packages.delete(package)


# ── Package items ──────────────────────────────────────────────────────────


@router.post(
    "/{package_id}/items",
    response_model=PackageItemAdminRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_super_admin)],
)
async def add_package_item(
    package_id: uuid.UUID,
    payload: PackageItemCreate,
    packages: PackageService = Depends(get_package_service),
) -> PackageItemAdminRead:
    package = await packages.get_by_id(package_id)
    if package is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Package not found"
        )
    return PackageItemAdminRead.model_validate(await packages.add_item(package, payload))


@router.patch(
    "/{package_id}/items/{item_id}",
    response_model=PackageItemAdminRead,
    dependencies=[Depends(require_super_admin)],
)
async def update_package_item(
    package_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: PackageItemUpdate,
    packages: PackageService = Depends(get_package_service),
) -> PackageItemAdminRead:
    item = await packages.get_item(item_id)
    if item is None or item.package_id != package_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Package item not found"
        )
    return PackageItemAdminRead.model_validate(await packages.update_item(item, payload))


@router.delete(
    "/{package_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_super_admin)],
)
async def delete_package_item(
    package_id: uuid.UUID,
    item_id: uuid.UUID,
    packages: PackageService = Depends(get_package_service),
) -> None:
    item = await packages.get_item(item_id)
    if item is None or item.package_id != package_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Package item not found"
        )
    await packages.delete_item(item)
