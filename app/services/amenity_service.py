import uuid
from collections.abc import Sequence

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.amenity import Amenity, TreatmentProgram
from app.models.sanatorium import Sanatorium
from app.models.user import User, UserRole
from app.schemas.amenity import (
    AmenityCreate,
    AmenityUpdate,
    TreatmentProgramCreate,
    TreatmentProgramUpdate,
)


class AmenityService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── amenities ──────────────────────────────────────────────────────────

    async def list_amenities(self, *, limit: int, offset: int) -> tuple[Sequence[Amenity], int]:
        base = select(Amenity)
        total = (await self.db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
        rows = (await self.db.execute(base.order_by(Amenity.category.asc(), Amenity.created_at.asc()).limit(limit).offset(offset))).scalars().all()
        return rows, total

    async def get_amenity(self, amenity_id: uuid.UUID) -> Amenity | None:
        return (await self.db.execute(select(Amenity).where(Amenity.id == amenity_id))).scalar_one_or_none()

    async def create_amenity(self, payload: AmenityCreate) -> Amenity:
        amenity = Amenity(
            name=payload.name.model_dump(exclude_none=True),
            category=payload.category,
            icon=payload.icon,
        )
        self.db.add(amenity)
        await self.db.commit()
        await self.db.refresh(amenity)
        return amenity

    async def update_amenity(self, amenity: Amenity, payload: AmenityUpdate) -> Amenity:
        data = payload.model_dump(exclude_unset=True)
        if "name" in data and data["name"] is not None:
            data["name"] = {k: v for k, v in data["name"].items() if v is not None}
        for field, value in data.items():
            setattr(amenity, field, value)
        await self.db.commit()
        await self.db.refresh(amenity)
        return amenity

    async def delete_amenity(self, amenity: Amenity) -> None:
        await self.db.delete(amenity)
        await self.db.commit()

    # ── treatment programs ─────────────────────────────────────────────────

    async def _load_program(self, program_id: uuid.UUID) -> TreatmentProgram | None:
        stmt = (
            select(TreatmentProgram)
            .options(selectinload(TreatmentProgram.amenities))
            .where(TreatmentProgram.id == program_id)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def list_programs(
        self, sanatorium_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[Sequence[TreatmentProgram], int]:
        base = (
            select(TreatmentProgram)
            .options(selectinload(TreatmentProgram.amenities))
            .where(TreatmentProgram.sanatorium_id == sanatorium_id)
        )
        total = (await self.db.execute(select(func.count()).select_from(
            select(TreatmentProgram).where(TreatmentProgram.sanatorium_id == sanatorium_id).subquery()
        ))).scalar_one()
        rows = (await self.db.execute(
            base.order_by(TreatmentProgram.min_nights.asc()).limit(limit).offset(offset)
        )).scalars().all()
        return rows, total

    async def create_program(self, payload: TreatmentProgramCreate, user: User) -> TreatmentProgram:
        sanatorium = await self._check_sanatorium_access(payload.sanatorium_id, user)
        if sanatorium is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sanatorium not found or not accessible")

        if payload.max_nights is not None and payload.max_nights < payload.min_nights:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="max_nights must be >= min_nights")

        amenities = await self._fetch_amenities(payload.amenity_ids)

        program = TreatmentProgram(
            sanatorium_id=payload.sanatorium_id,
            name=payload.name.model_dump(exclude_none=True),
            min_nights=payload.min_nights,
            max_nights=payload.max_nights,
            amenities=amenities,
        )
        self.db.add(program)
        await self.db.commit()
        return await self._load_program(program.id)  # type: ignore[return-value]

    async def update_program(
        self, program: TreatmentProgram, payload: TreatmentProgramUpdate, user: User
    ) -> TreatmentProgram:
        await self._check_sanatorium_access(program.sanatorium_id, user)

        data = payload.model_dump(exclude_unset=True)
        amenity_ids = data.pop("amenity_ids", None)

        if "name" in data and data["name"] is not None:
            data["name"] = {k: v for k, v in data["name"].items() if v is not None}

        min_nights = data.get("min_nights", program.min_nights)
        max_nights = data.get("max_nights", program.max_nights)
        if max_nights is not None and max_nights < min_nights:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="max_nights must be >= min_nights")

        for field, value in data.items():
            setattr(program, field, value)

        if amenity_ids is not None:
            program.amenities = await self._fetch_amenities(amenity_ids)

        await self.db.commit()
        return await self._load_program(program.id)  # type: ignore[return-value]

    async def delete_program(self, program: TreatmentProgram) -> None:
        await self.db.delete(program)
        await self.db.commit()

    async def _fetch_amenities(self, amenity_ids: list[uuid.UUID]) -> list[Amenity]:
        if not amenity_ids:
            return []
        rows = (await self.db.execute(select(Amenity).where(Amenity.id.in_(amenity_ids)))).scalars().all()
        if len(rows) != len(amenity_ids):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="One or more amenity IDs not found")
        return list(rows)

    async def _check_sanatorium_access(self, sanatorium_id: uuid.UUID, user: User) -> Sanatorium | None:
        sanatorium = (await self.db.execute(
            select(Sanatorium).where(Sanatorium.id == sanatorium_id)
        )).scalar_one_or_none()
        if sanatorium is None:
            return None
        if user.role == UserRole.SUPER_ADMIN:
            return sanatorium
        if user.role == UserRole.ADMIN and sanatorium.admin_user_id == user.id:
            return sanatorium
        return None


def get_amenity_service(db: AsyncSession = Depends(get_db)) -> AmenityService:
    return AmenityService(db)
