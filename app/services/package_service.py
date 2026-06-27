import uuid
from collections.abc import Sequence
from decimal import Decimal

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.db_utils import assert_fk
from app.core.ids import uuid7
from app.core.pagination import paginated
from app.core.permissions import (
    PACKAGE_SUPER_ADMIN_ONLY_FIELDS,
    assert_sanatorium_access,
    assert_super_admin_only_fields,
)
from app.core.slug import resolve_unique_slug, slugify
from app.core.storage import MIME_EXTENSIONS, StorageBackend, url_to_key
from app.core.utils import merge_translation_fields, pick_locale
from app.models.package import Package, PackageItem
from app.models.room import Room
from app.models.sanatorium import Sanatorium
from app.models.user import User, UserRole
from app.schemas.package import (
    PackageCreate,
    PackageItemCreate,
    PackageItemUpdate,
    PackageUpdate,
)


def _slug(text: str) -> str:
    return slugify(text, fallback="package")


class PackageService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, package_id: uuid.UUID) -> Package | None:
        return await self.db.scalar(
            select(Package)
            .options(selectinload(Package.items))
            .where(Package.id == package_id)
        )

    async def get_by_slug(self, slug: str) -> Package | None:
        return await self.db.scalar(
            select(Package)
            .options(selectinload(Package.items))
            .where(Package.slug == slug)
        )

    async def list_packages(
        self,
        *,
        limit: int,
        offset: int,
        active_only: bool = True,
        featured_only: bool = False,
        sanatorium_id: uuid.UUID | None = None,
        duration_min: int | None = None,
        duration_max: int | None = None,
        price_min: Decimal | None = None,
        price_max: Decimal | None = None,
    ) -> tuple[Sequence[Package], int]:
        stmt = select(Package).options(selectinload(Package.items))
        if active_only:
            stmt = stmt.where(Package.is_active.is_(True))
        if featured_only:
            stmt = stmt.where(Package.is_featured.is_(True))
        if sanatorium_id is not None:
            stmt = stmt.where(Package.sanatorium_id == sanatorium_id)
        if duration_min is not None:
            stmt = stmt.where(Package.duration_nights >= duration_min)
        if duration_max is not None:
            stmt = stmt.where(Package.duration_nights <= duration_max)
        if price_min is not None:
            stmt = stmt.where(Package.base_price >= price_min)
        if price_max is not None:
            stmt = stmt.where(Package.base_price <= price_max)
        stmt = stmt.order_by(
            Package.display_order.asc(),
            Package.created_at.desc(),
        )
        return await paginated(self.db, stmt, limit=limit, offset=offset)

    async def create(self, payload: PackageCreate, user: User | None) -> Package:
        if user is None or user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only sanatorium admins can create packages",
            )
        title_dict = payload.title.model_dump()
        slug_seed = payload.slug or pick_locale(title_dict)
        slug = await resolve_unique_slug(self.db, Package, _slug(slug_seed))

        await assert_fk(self.db, Sanatorium, payload.sanatorium_id, "sanatorium_id")
        await assert_sanatorium_access(
            self.db,
            payload.sanatorium_id,
            user,
            action="create packages for this sanatorium",
        )
        await self._require_room(
            payload.room_id, payload.sanatorium_id, payload.currency
        )

        package = Package(
            slug=slug,
            title=title_dict,
            description=payload.description.model_dump(),
            duration_nights=payload.duration_nights,
            base_price=payload.base_price,
            currency=payload.currency,
            sanatorium_id=payload.sanatorium_id,
            room_id=payload.room_id,
        )
        for item_payload in payload.items:
            package.items.append(self._build_item(item_payload))

        self.db.add(package)
        await self.db.commit()
        return await self._reload_required(package.id)

    async def update(
        self, package: Package, payload: PackageUpdate, user: User
    ) -> Package:
        await self._assert_can_manage(package, user)
        data = payload.model_dump(exclude_unset=True)
        assert_super_admin_only_fields(
            data, user, restricted_fields=PACKAGE_SUPER_ADMIN_ONLY_FIELDS
        )
        merge_translation_fields(package, data, ("title", "description"))

        if "slug" in data and data["slug"] is not None:
            data["slug"] = await resolve_unique_slug(
                self.db, Package, _slug(data["slug"]), exclude_id=package.id
            )
        elif "title" in data and "slug" not in data:
            data["slug"] = await resolve_unique_slug(
                self.db,
                Package,
                _slug(pick_locale(data["title"])),
                exclude_id=package.id,
            )

        new_room_id = data.get("room_id", package.room_id)
        new_currency = data.get("currency", package.currency)
        if "room_id" in data or "currency" in data:
            await self._require_room(new_room_id, package.sanatorium_id, new_currency)

        for field, value in data.items():
            setattr(package, field, value)
        await self.db.commit()
        return await self._reload_required(package.id)

    async def delete(self, package: Package) -> None:
        await self.db.delete(package)
        await self.db.commit()

    async def _assert_can_manage(self, package: Package, user: User) -> None:
        """Super_admin always; sanatorium admin only for their own property."""
        await assert_sanatorium_access(
            self.db,
            package.sanatorium_id,
            user,
            action="manage this package",
        )

    async def update_hero_image(
        self,
        package: Package,
        *,
        content: bytes,
        content_type: str,
        storage: StorageBackend,
        user: User,
    ) -> Package:
        await self._assert_can_manage(package, user)
        await self._delete_local_hero_image(package, storage)
        ext = MIME_EXTENSIONS[content_type]
        image_id = uuid7()
        key = f"packages/{package.id}/{image_id}.{ext}"
        package.hero_image_url = await storage.save(
            key=key, content=content, content_type=content_type
        )
        await self.db.commit()
        return await self._reload_required(package.id)

    async def delete_hero_image(
        self, package: Package, storage: StorageBackend, user: User
    ) -> Package:
        await self._assert_can_manage(package, user)
        await self._delete_local_hero_image(package, storage)
        package.hero_image_url = None
        await self.db.commit()
        return await self._reload_required(package.id)

    async def get_item(self, item_id: uuid.UUID) -> PackageItem | None:
        return await self.db.get(PackageItem, item_id)

    async def add_item(
        self, package: Package, payload: PackageItemCreate, user: User
    ) -> PackageItem:
        await self._assert_can_manage(package, user)
        item = self._build_item(payload)
        item.package_id = package.id
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def update_item(
        self, item: PackageItem, payload: PackageItemUpdate, user: User
    ) -> PackageItem:
        await self._assert_item_can_manage(item, user)
        data = payload.model_dump(exclude_unset=True)
        merge_translation_fields(item, data, ("title", "description"))
        for field, value in data.items():
            setattr(item, field, value)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def delete_item(self, item: PackageItem, user: User) -> None:
        await self._assert_item_can_manage(item, user)
        await self.db.delete(item)
        await self.db.commit()

    async def _assert_item_can_manage(self, item: PackageItem, user: User) -> None:
        sanatorium_id = await self.db.scalar(
            select(Package.sanatorium_id).where(Package.id == item.package_id)
        )
        if sanatorium_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Package not found"
            )
        await assert_sanatorium_access(
            self.db, sanatorium_id, user, action="manage this package"
        )

    async def _require_room(
        self,
        room_id: uuid.UUID,
        sanatorium_id: uuid.UUID,
        currency: str,
    ) -> None:
        room = await self.db.get(Room, room_id)
        if room is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="room_id not found",
            )
        if room.sanatorium_id != sanatorium_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="room_id does not belong to the package's sanatorium",
            )
        if not room.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="room_id refers to an inactive room",
            )
        if room.base_currency != currency:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Room currency {room.base_currency} does not match "
                    f"package currency {currency}"
                ),
            )

    @staticmethod
    def _build_item(payload: PackageItemCreate) -> PackageItem:
        return PackageItem(
            item_type=payload.item_type,
            title=payload.title.model_dump(),
            description=payload.description.model_dump(exclude_none=True),
            is_included=payload.is_included,
            extra_price=payload.extra_price,
            display_order=payload.display_order,
        )

    async def _reload_required(self, package_id: uuid.UUID) -> Package:
        package = await self.get_by_id(package_id)
        if package is None:
            raise RuntimeError(f"Package {package_id} not found after write")
        return package

    @staticmethod
    async def _delete_local_hero_image(
        package: Package, storage: StorageBackend
    ) -> None:
        url = package.hero_image_url
        prefix = settings.UPLOAD_URL_PREFIX.rstrip("/") + "/"
        if url and url.startswith(prefix):
            await storage.delete(key=url_to_key(url))


def get_package_service(db: AsyncSession = Depends(get_db)) -> PackageService:
    return PackageService(db)
