import uuid
from collections.abc import Sequence

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.pagination import paginated
from app.core.permissions import assert_sanatorium_access
from app.core.utils import strip_translation_fields
from app.models.amenity import Amenity
from app.models.program import TreatmentProgram
from app.models.user import User
from app.schemas.amenity import TreatmentProgramCreate, TreatmentProgramUpdate

_TRANSLATION_FIELDS = ("name", "description", "instructor_bio", "what_to_bring")
_ACTION = "manage this sanatorium's programs"


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
        stmt = (
            select(TreatmentProgram)
            .options(selectinload(TreatmentProgram.amenities))
            .where(TreatmentProgram.sanatorium_id == sanatorium_id)
            .order_by(TreatmentProgram.created_at.asc())
        )
        return await paginated(self.db, stmt, limit=limit, offset=offset)

    async def create(
        self, payload: TreatmentProgramCreate, user: User
    ) -> TreatmentProgram:
        await assert_sanatorium_access(
            self.db, payload.sanatorium_id, user, action=_ACTION
        )
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
        await assert_sanatorium_access(
            self.db, program.sanatorium_id, user, action=_ACTION
        )

        data = payload.model_dump(exclude_unset=True)
        amenity_ids = data.pop("amenity_ids", None)
        strip_translation_fields(data, _TRANSLATION_FIELDS)

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
        await assert_sanatorium_access(
            self.db, program.sanatorium_id, user, action=_ACTION
        )
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

    @staticmethod
    def _validate_nights(min_nights: int | None, max_nights: int | None) -> None:
        if min_nights is not None and max_nights is not None and max_nights < min_nights:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="max_nights must be >= min_nights",
            )


def get_program_service(db: AsyncSession = Depends(get_db)) -> ProgramService:
    return ProgramService(db)
