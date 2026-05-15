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
from app.schemas.amenity import TreatmentProgramCreate, TreatmentProgramUpdate

_TRANSLATION_FIELDS = ("name", "description", "instructor_bio", "what_to_bring")


def _strip_empty_translations(data: dict) -> None:
    for field in _TRANSLATION_FIELDS:
        if field in data and data[field] is not None:
            data[field] = {k: v for k, v in data[field].items() if v is not None}


class ProgramService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, program_id: uuid.UUID) -> TreatmentProgram | None:
        stmt = (
            select(TreatmentProgram)
            .options(selectinload(TreatmentProgram.amenities))
            .where(TreatmentProgram.id == program_id)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def list_for_sanatorium(
        self, sanatorium_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[Sequence[TreatmentProgram], int]:
        base = (
            select(TreatmentProgram)
            .options(selectinload(TreatmentProgram.amenities))
            .where(TreatmentProgram.sanatorium_id == sanatorium_id)
        )
        total = (
            await self.db.execute(
                select(func.count()).select_from(base.subquery())
            )
        ).scalar_one()
        stmt = base.order_by(TreatmentProgram.created_at.asc()).limit(limit).offset(offset)
        rows = (await self.db.execute(stmt)).scalars().all()
        return rows, total

    async def create(
        self, payload: TreatmentProgramCreate, user: User
    ) -> TreatmentProgram:
        await self._assert_can_manage(payload.sanatorium_id, user)
        self._validate_nights(payload.min_nights, payload.max_nights)
        if (payload.price is None) != (payload.currency is None):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="price and currency must be set together",
            )

        amenities = await self._fetch_amenities(payload.amenity_ids)

        program = TreatmentProgram(
            sanatorium_id=payload.sanatorium_id,
            name=payload.name.model_dump(exclude_none=True),
            description=payload.description.model_dump(exclude_none=True),
            min_nights=payload.min_nights,
            max_nights=payload.max_nights,
            duration_minutes=payload.duration_minutes,
            price=payload.price,
            currency=payload.currency,
            instructor_name=payload.instructor_name,
            instructor_bio=payload.instructor_bio.model_dump(exclude_none=True),
            group_size_min=payload.group_size_min,
            group_size_max=payload.group_size_max,
            what_to_bring=payload.what_to_bring.model_dump(exclude_none=True),
            amenities=amenities,
        )
        self.db.add(program)
        await self.db.commit()
        return await self.get_by_id(program.id)  # type: ignore[return-value]

    async def update(
        self,
        program: TreatmentProgram,
        payload: TreatmentProgramUpdate,
        user: User,
    ) -> TreatmentProgram:
        await self._assert_can_manage(program.sanatorium_id, user)

        data = payload.model_dump(exclude_unset=True)
        amenity_ids = data.pop("amenity_ids", None)
        _strip_empty_translations(data)

        self._validate_nights(
            data.get("min_nights", program.min_nights),
            data.get("max_nights", program.max_nights),
        )

        for field, value in data.items():
            setattr(program, field, value)
        if amenity_ids is not None:
            program.amenities = await self._fetch_amenities(amenity_ids)

        await self.db.commit()
        return await self.get_by_id(program.id)  # type: ignore[return-value]

    async def delete(self, program: TreatmentProgram, user: User) -> None:
        await self._assert_can_manage(program.sanatorium_id, user)
        await self.db.delete(program)
        await self.db.commit()

    async def _fetch_amenities(
        self, amenity_ids: list[uuid.UUID]
    ) -> list[Amenity]:
        if not amenity_ids:
            return []
        rows = (
            await self.db.execute(
                select(Amenity).where(Amenity.id.in_(amenity_ids))
            )
        ).scalars().all()
        if len(rows) != len(amenity_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more amenity IDs not found",
            )
        return list(rows)

    async def _assert_can_manage(
        self, sanatorium_id: uuid.UUID, user: User
    ) -> Sanatorium:
        sanatorium = (
            await self.db.execute(
                select(Sanatorium).where(Sanatorium.id == sanatorium_id)
            )
        ).scalar_one_or_none()
        if sanatorium is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sanatorium not found",
            )
        if user.role == UserRole.SUPER_ADMIN:
            return sanatorium
        if user.role == UserRole.ADMIN and sanatorium.admin_user_id == user.id:
            return sanatorium
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to manage this sanatorium's programs",
        )

    @staticmethod
    def _validate_nights(min_nights: int | None, max_nights: int | None) -> None:
        if min_nights is not None and max_nights is not None and max_nights < min_nights:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="max_nights must be >= min_nights",
            )


def get_program_service(db: AsyncSession = Depends(get_db)) -> ProgramService:
    return ProgramService(db)
