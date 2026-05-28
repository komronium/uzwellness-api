import uuid
from collections.abc import Sequence

from fastapi import Depends, HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.ids import uuid7
from app.core.pagination import paginated
from app.core.slug import resolve_unique_slug, slugify
from app.core.storage import MIME_EXTENSIONS, StorageBackend, url_to_key
from app.core.utils import merge_translation_fields, pick_locale
from app.models.program import TreatmentFocus, TreatmentProgram
from app.models.sanatorium import Sanatorium, SanatoriumStatus
from app.schemas.treatment_focus import TreatmentFocusCreate, TreatmentFocusUpdate


def _slug(text: str) -> str:
    return slugify(text, fallback="treatment-focus")


class TreatmentFocusService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_all(
        self,
        *,
        limit: int,
        offset: int,
        active_only: bool = False,
    ) -> tuple[Sequence[TreatmentFocus], int]:
        stmt = select(TreatmentFocus).order_by(
            TreatmentFocus.display_order.asc(), TreatmentFocus.created_at.asc()
        )
        if active_only:
            stmt = stmt.where(TreatmentFocus.is_active.is_(True))
        return await paginated(self.db, stmt, limit=limit, offset=offset)

    async def list_tiles(self) -> list[tuple[TreatmentFocus, int, int]]:
        stmt = (
            select(
                TreatmentFocus,
                func.count(
                    func.distinct(
                        case(
                            (Sanatorium.id.is_not(None), TreatmentProgram.id),
                            else_=None,
                        )
                    )
                ).label("programs_count"),
                func.count(func.distinct(Sanatorium.id)).label("sanatoriums_count"),
            )
            .select_from(TreatmentFocus)
            .outerjoin(
                TreatmentProgram,
                (TreatmentProgram.focus_id == TreatmentFocus.id)
                & (TreatmentProgram.is_active.is_(True)),
            )
            .outerjoin(
                Sanatorium,
                (TreatmentProgram.sanatorium_id == Sanatorium.id)
                & (Sanatorium.status == SanatoriumStatus.APPROVED),
            )
            .where(TreatmentFocus.is_active.is_(True))
            .group_by(TreatmentFocus.id)
            .order_by(TreatmentFocus.display_order.asc(), TreatmentFocus.created_at.asc())
        )
        rows = (await self.db.execute(stmt)).all()
        return [
            (focus, int(programs), int(sanatoriums))
            for focus, programs, sanatoriums in rows
        ]

    async def get_by_id(self, focus_id: uuid.UUID) -> TreatmentFocus | None:
        return await self.db.get(TreatmentFocus, focus_id)

    async def get_by_slug(self, slug: str) -> TreatmentFocus | None:
        return await self.db.scalar(
            select(TreatmentFocus).where(TreatmentFocus.slug == slug)
        )

    async def create(self, payload: TreatmentFocusCreate) -> TreatmentFocus:
        name_dict = payload.name.model_dump()
        slug_seed = payload.slug or pick_locale(name_dict)
        if not slug_seed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="name must contain at least one locale",
            )
        focus = TreatmentFocus(
            slug=await resolve_unique_slug(self.db, TreatmentFocus, _slug(slug_seed)),
            name=name_dict,
            description=payload.description.model_dump(exclude_none=True),
            icon=payload.icon,
            display_order=payload.display_order,
            is_active=payload.is_active,
        )
        self.db.add(focus)
        await self.db.commit()
        await self.db.refresh(focus)
        return focus

    async def update(
        self, focus: TreatmentFocus, payload: TreatmentFocusUpdate
    ) -> TreatmentFocus:
        data = payload.model_dump(exclude_unset=True)
        merge_translation_fields(focus, data, ("name", "description"))

        if "slug" in data and data["slug"] is not None:
            data["slug"] = await resolve_unique_slug(
                self.db, TreatmentFocus, _slug(data["slug"]), exclude_id=focus.id
            )
        elif "name" in data and "slug" not in data:
            data["slug"] = await resolve_unique_slug(
                self.db,
                TreatmentFocus,
                _slug(pick_locale(data["name"])),
                exclude_id=focus.id,
            )

        for field, value in data.items():
            setattr(focus, field, value)
        await self.db.commit()
        await self.db.refresh(focus)
        return focus

    async def update_image(
        self,
        focus: TreatmentFocus,
        *,
        content: bytes,
        content_type: str,
        storage: StorageBackend,
    ) -> TreatmentFocus:
        await self._delete_local_image(focus, storage)
        ext = MIME_EXTENSIONS[content_type]
        image_id = uuid7()
        key = f"treatment-focuses/{focus.id}/{image_id}.{ext}"
        focus.image_url = await storage.save(
            key=key, content=content, content_type=content_type
        )
        await self.db.commit()
        await self.db.refresh(focus)
        return focus

    async def delete_image(
        self, focus: TreatmentFocus, storage: StorageBackend
    ) -> TreatmentFocus:
        await self._delete_local_image(focus, storage)
        focus.image_url = None
        await self.db.commit()
        await self.db.refresh(focus)
        return focus

    async def delete(self, focus: TreatmentFocus) -> None:
        await self.db.delete(focus)
        await self.db.commit()

    @staticmethod
    async def _delete_local_image(
        focus: TreatmentFocus, storage: StorageBackend
    ) -> None:
        url = focus.image_url
        prefix = settings.UPLOAD_URL_PREFIX.rstrip("/") + "/"
        if url and url.startswith(prefix):
            await storage.delete(key=url_to_key(url))


def get_treatment_focus_service(
    db: AsyncSession = Depends(get_db),
) -> TreatmentFocusService:
    return TreatmentFocusService(db)
