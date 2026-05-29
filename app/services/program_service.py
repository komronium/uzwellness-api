import uuid
from collections.abc import Sequence

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.db_utils import fetch_by_ids
from app.core.pagination import paginated
from app.core.permissions import assert_sanatorium_access
from app.core.utils import merge_translation_fields
from app.models.amenity import Amenity
from app.models.program import TreatmentFocus, TreatmentProgram
from app.models.user import User
from app.schemas.program import TreatmentProgramCreate, TreatmentProgramUpdate

_TRANSLATION_FIELDS = ("name", "description", "instructor_bio", "what_to_bring")
_ACTION = "manage this sanatorium's programs"


class ProgramService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, program_id: uuid.UUID) -> TreatmentProgram | None:
        return await self.db.scalar(
            select(TreatmentProgram)
            .options(selectinload(TreatmentProgram.amenities))
            .where(TreatmentProgram.id == program_id)
        )

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
        self._assert_price_currency_pair(payload.price, payload.currency)
        if payload.focus_id is not None:
            await self._assert_focus_exists(payload.focus_id)

        amenities = await fetch_by_ids(
            self.db, Amenity, payload.amenity_ids, label="amenity"
        )

        program = TreatmentProgram(
            sanatorium_id=payload.sanatorium_id,
            focus_id=payload.focus_id,
            name=payload.name.model_dump(),
            description=payload.description.model_dump(),
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
        merge_translation_fields(program, data, _TRANSLATION_FIELDS)

        self._validate_nights(
            data.get("min_nights", program.min_nights),
            data.get("max_nights", program.max_nights),
        )

        final_price = data.get("price", program.price)
        final_currency = data.get("currency", program.currency)
        self._assert_price_currency_pair(final_price, final_currency)
        if "focus_id" in data and data["focus_id"] is not None:
            await self._assert_focus_exists(data["focus_id"])

        for field, value in data.items():
            setattr(program, field, value)
        if amenity_ids is not None:
            program.amenities = await fetch_by_ids(
                self.db, Amenity, amenity_ids, label="amenity"
            )

        await self.db.commit()
        return await self.get_by_id(program.id)  # type: ignore[return-value]

    async def delete(self, program: TreatmentProgram, user: User) -> None:
        await assert_sanatorium_access(
            self.db, program.sanatorium_id, user, action=_ACTION
        )
        await self.db.delete(program)
        await self.db.commit()

    @staticmethod
    def _validate_nights(min_nights: int | None, max_nights: int | None) -> None:
        if (
            min_nights is not None
            and max_nights is not None
            and max_nights < min_nights
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="max_nights must be >= min_nights",
            )

    @staticmethod
    def _assert_price_currency_pair(price, currency) -> None:
        if (price is None) != (currency is None):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="price and currency must be set together",
            )

    async def _assert_focus_exists(self, focus_id: uuid.UUID) -> None:
        focus = await self.db.get(TreatmentFocus, focus_id)
        if focus is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Treatment focus not found",
            )


def get_program_service(db: AsyncSession = Depends(get_db)) -> ProgramService:
    return ProgramService(db)
