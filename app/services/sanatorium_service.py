import re
import unicodedata
import uuid
from collections.abc import Sequence

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.amenity import Amenity
from app.models.sanatorium import Sanatorium, SanatoriumImage, SanatoriumStatus
from app.models.user import User, UserRole
from app.schemas.sanatorium import SanatoriumCreate, SanatoriumUpdate
from app.services.storage import MIME_EXTENSIONS, StorageBackend

_UZBEK_STRIP = str.maketrans({"ʻ": "", "ʼ": "", "'": "", "'": ""})


def slugify(text: str) -> str:
    text = text.translate(_UZBEK_STRIP)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text or "sanatorium"


class SanatoriumService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, sanatorium_id: uuid.UUID) -> Sanatorium | None:
        return await self._reload(sanatorium_id)

    async def get_by_slug(self, slug: str) -> Sanatorium | None:
        stmt = select(Sanatorium).where(Sanatorium.slug == slug)
        obj = (await self.db.execute(stmt)).scalar_one_or_none()
        return await self._reload(obj.id) if obj else None

    async def _resolve_slug(
        self, base: str, exclude_id: uuid.UUID | None = None
    ) -> str:
        candidate = base
        suffix = 2
        while True:
            existing = (await self.db.execute(
                select(Sanatorium).where(Sanatorium.slug == candidate)
            )).scalar_one_or_none()
            if existing is None or existing.id == exclude_id:
                return candidate
            candidate = f"{base}-{suffix}"
            suffix += 1

    async def create(self, payload: SanatoriumCreate) -> Sanatorium:
        base_slug = slugify(payload.slug or payload.name)
        slug = await self._resolve_slug(base_slug)

        amenities = await self._fetch_amenities(payload.amenity_ids)

        sanatorium = Sanatorium(
            name=payload.name,
            slug=slug,
            description=payload.description.model_dump(exclude_none=True),
            city=payload.city,
            address=payload.address,
            lat=payload.lat,
            lng=payload.lng,
            phone=payload.phone,
            stars=payload.stars,
            treatment_focuses=payload.treatment_focuses,
            admin_user_id=payload.admin_user_id,
            status=SanatoriumStatus.PENDING,
            amenities=amenities,
        )
        self.db.add(sanatorium)
        await self.db.commit()
        return await self._reload(sanatorium.id)

    async def update(
        self, sanatorium: Sanatorium, payload: SanatoriumUpdate
    ) -> Sanatorium:
        data = payload.model_dump(exclude_unset=True)

        amenity_ids = data.pop("amenity_ids", None)

        if "description" in data and data["description"] is not None:
            data["description"] = {
                k: v for k, v in data["description"].items() if v is not None
            }

        if "slug" in data and data["slug"] is not None:
            base_slug = slugify(data["slug"])
            data["slug"] = await self._resolve_slug(base_slug, exclude_id=sanatorium.id)
        elif "name" in data and "slug" not in data:
            base_slug = slugify(data["name"])
            data["slug"] = await self._resolve_slug(base_slug, exclude_id=sanatorium.id)

        for field, value in data.items():
            setattr(sanatorium, field, value)

        if amenity_ids is not None:
            sanatorium.amenities = await self._fetch_amenities(amenity_ids)

        await self.db.commit()
        return await self._reload(sanatorium.id)

    async def approve(self, sanatorium: Sanatorium) -> Sanatorium:
        if sanatorium.status == SanatoriumStatus.APPROVED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Sanatorium already approved",
            )
        sanatorium.status = SanatoriumStatus.APPROVED
        await self.db.commit()
        return await self._reload(sanatorium.id)

    async def get_visible(
        self, sanatorium_id: uuid.UUID, user: User | None
    ) -> Sanatorium | None:
        sanatorium = await self.get_by_id(sanatorium_id)
        if sanatorium is None or not _can_view(sanatorium, user):
            return None
        return sanatorium

    async def list_for_user(
        self,
        *,
        user: User | None,
        limit: int,
        offset: int,
        city: str | None = None,
        status_filter: SanatoriumStatus | None = None,
        stars: int | None = None,
        q: str | None = None,
        sort: str = "-created_at",
        amenity_ids: list[uuid.UUID] | None = None,
        treatment_focus: str | None = None,
    ) -> tuple[Sequence[Sanatorium], int]:
        base = select(Sanatorium)
        base = _apply_visibility(base, user)

        if city is not None:
            base = base.where(Sanatorium.city == city)
        if status_filter is not None:
            base = base.where(Sanatorium.status == status_filter)
        if stars is not None:
            base = base.where(Sanatorium.stars == stars)
        if q is not None and q.strip():
            base = base.where(Sanatorium.name.icontains(q.strip(), autoescape=True))
        if treatment_focus is not None:
            base = base.where(Sanatorium.treatment_focuses.contains([treatment_focus]))
        if amenity_ids:
            # Sanatorium must have ALL requested amenities
            for aid in amenity_ids:
                sub = (
                    select(Sanatorium.id)
                    .join(Sanatorium.amenities)
                    .where(Amenity.id == aid)
                    .scalar_subquery()
                )
                base = base.where(Sanatorium.id.in_(sub))

        total_stmt = select(func.count()).select_from(base.subquery())
        total = (await self.db.execute(total_stmt)).scalar_one()

        stmt = (
            base.options(
                selectinload(Sanatorium.images),
                selectinload(Sanatorium.amenities),
            )
            .order_by(_SORT_CLAUSES.get(sort, Sanatorium.created_at.desc()))
            .limit(limit)
            .offset(offset)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return rows, total

    async def add_image(
        self,
        *,
        sanatorium: Sanatorium,
        content: bytes,
        content_type: str,
        storage: StorageBackend,
        caption: str | None,
        is_primary: bool,
        order: int,
    ) -> SanatoriumImage:
        ext = MIME_EXTENSIONS[content_type]
        image_id = uuid.uuid4()
        key = f"sanatoriums/{sanatorium.id}/{image_id}.{ext}"
        url = await storage.save(key=key, content=content, content_type=content_type)

        if is_primary:
            await self.db.execute(
                update(SanatoriumImage)
                .where(SanatoriumImage.sanatorium_id == sanatorium.id)
                .where(SanatoriumImage.is_primary.is_(True))
                .values(is_primary=False)
            )

        image = SanatoriumImage(
            id=image_id,
            sanatorium_id=sanatorium.id,
            url=url,
            order=order,
            is_primary=is_primary,
            caption=caption,
        )
        self.db.add(image)
        await self.db.commit()
        await self.db.refresh(image)
        return image

    async def _reload(self, sanatorium_id: uuid.UUID) -> Sanatorium | None:
        stmt = (
            select(Sanatorium)
            .where(Sanatorium.id == sanatorium_id)
            .options(
                selectinload(Sanatorium.images),
                selectinload(Sanatorium.amenities),
            )
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _fetch_amenities(self, amenity_ids: list[uuid.UUID]) -> list[Amenity]:
        if not amenity_ids:
            return []
        rows = (await self.db.execute(
            select(Amenity).where(Amenity.id.in_(amenity_ids))
        )).scalars().all()
        if len(rows) != len(amenity_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more amenity IDs not found",
            )
        return list(rows)


_SORT_CLAUSES = {
    "name": Sanatorium.name.asc(),
    "-name": Sanatorium.name.desc(),
    "stars": Sanatorium.stars.asc(),
    "-stars": Sanatorium.stars.desc(),
    "rating": Sanatorium.avg_rating.asc(),
    "-rating": Sanatorium.avg_rating.desc(),
    "created_at": Sanatorium.created_at.asc(),
    "-created_at": Sanatorium.created_at.desc(),
}

SORT_FIELDS = tuple(_SORT_CLAUSES.keys())


def _apply_visibility(stmt, user: User | None):
    if user is None or user.role in (UserRole.CUSTOMER, UserRole.AGENT):
        return stmt.where(Sanatorium.status == SanatoriumStatus.APPROVED)
    if user.role == UserRole.ADMIN:
        return stmt.where(Sanatorium.admin_user_id == user.id)
    return stmt


def _can_view(sanatorium: Sanatorium, user: User | None) -> bool:
    if user is not None and user.role == UserRole.SUPER_ADMIN:
        return True
    if user is not None and user.role == UserRole.ADMIN:
        return sanatorium.admin_user_id == user.id
    return sanatorium.status == SanatoriumStatus.APPROVED


def get_sanatorium_service(db: AsyncSession = Depends(get_db)) -> SanatoriumService:
    return SanatoriumService(db)
