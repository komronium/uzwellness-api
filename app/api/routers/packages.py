import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Query, UploadFile, status

from app.api.deps import (
    CurrentUser,
    IncludeTranslationsDep,
    LocaleDep,
    OptionalUser,
    not_found,
    require_roles,
)
from app.core.pagination import Pagination
from app.core.storage import StorageBackend, get_storage
from app.core.uploads import read_image_upload_as_webp
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

router = APIRouter(prefix="/packages", tags=["Packages"])

require_super_admin = require_roles(UserRole.SUPER_ADMIN)
require_sanatorium_admin = require_roles(UserRole.ADMIN)


@router.get("", response_model=PackageList | PackageAdminList)
async def list_packages(
    current_user: OptionalUser,
    locale: LocaleDep,
    include_translations: IncludeTranslationsDep,
    page: Pagination,
    active_only: bool = Query(default=True),
    sanatorium_id: uuid.UUID | None = Query(default=None),
    duration_min: int | None = Query(default=None, ge=1),
    duration_max: int | None = Query(default=None, ge=1),
    price_min: Decimal | None = Query(default=None, ge=0),
    price_max: Decimal | None = Query(default=None, ge=0),
    packages: PackageService = Depends(get_package_service),
) -> PackageList | PackageAdminList:
    is_super_admin = (
        current_user is not None and current_user.role == UserRole.SUPER_ADMIN
    )
    items, total = await packages.list_packages(
        limit=page.limit,
        offset=page.offset,
        active_only=active_only or not is_super_admin,
        sanatorium_id=sanatorium_id,
        duration_min=duration_min,
        duration_max=duration_max,
        price_min=price_min,
        price_max=price_max,
    )
    if include_translations and is_super_admin:
        return PackageAdminList(
            items=[PackageAdminRead.model_validate(p) for p in items],
            total=total,
            limit=page.limit,
            offset=page.offset,
        )
    return PackageList(
        items=[PackageRead.from_obj(p, locale) for p in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/featured", response_model=PackageList)
async def list_featured_packages(
    locale: LocaleDep,
    page: Pagination,
    packages: PackageService = Depends(get_package_service),
) -> PackageList:
    items, total = await packages.list_packages(
        limit=page.limit,
        offset=page.offset,
        active_only=True,
        featured_only=True,
    )
    return PackageList(
        items=[PackageRead.from_obj(p, locale) for p in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{package_id_or_slug}", response_model=PackageRead | PackageAdminRead)
async def get_package(
    package_id_or_slug: str,
    current_user: OptionalUser,
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
        raise not_found("Package not found")
    is_super_admin = (
        current_user is not None and current_user.role == UserRole.SUPER_ADMIN
    )
    if not package.is_active and not is_super_admin:
        raise not_found("Package not found")
    if include_translations and is_super_admin:
        return PackageAdminRead.model_validate(package)
    return PackageRead.from_obj(package, locale)


@router.post(
    "",
    response_model=PackageAdminRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_sanatorium_admin)],
)
async def create_package(
    payload: PackageCreate,
    current_user: CurrentUser,
    packages: PackageService = Depends(get_package_service),
) -> PackageAdminRead:
    return PackageAdminRead.model_validate(await packages.create(payload, current_user))


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
        raise not_found("Package not found")
    return PackageAdminRead.model_validate(await packages.update(package, payload))


@router.post(
    "/{package_id}/hero-image",
    response_model=PackageAdminRead,
    dependencies=[Depends(require_super_admin)],
)
async def upload_package_hero_image(
    package_id: uuid.UUID,
    file: UploadFile = File(...),
    packages: PackageService = Depends(get_package_service),
    storage: StorageBackend = Depends(get_storage),
) -> PackageAdminRead:
    package = await packages.get_by_id(package_id)
    if package is None:
        raise not_found("Package not found")
    content, mime = await read_image_upload_as_webp(file)
    updated = await packages.update_hero_image(
        package,
        content=content,
        content_type=mime,
        storage=storage,
    )
    return PackageAdminRead.model_validate(updated)


@router.delete(
    "/{package_id}/hero-image",
    response_model=PackageAdminRead,
    dependencies=[Depends(require_super_admin)],
)
async def delete_package_hero_image(
    package_id: uuid.UUID,
    packages: PackageService = Depends(get_package_service),
    storage: StorageBackend = Depends(get_storage),
) -> PackageAdminRead:
    package = await packages.get_by_id(package_id)
    if package is None:
        raise not_found("Package not found")
    updated = await packages.delete_hero_image(package, storage)
    return PackageAdminRead.model_validate(updated)


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
        raise not_found("Package not found")
    await packages.delete(package)


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
        raise not_found("Package not found")
    return PackageItemAdminRead.model_validate(
        await packages.add_item(package, payload)
    )


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
        raise not_found("Package item not found")
    return PackageItemAdminRead.model_validate(
        await packages.update_item(item, payload)
    )


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
        raise not_found("Package item not found")
    await packages.delete_item(item)
