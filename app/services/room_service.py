import uuid
from collections.abc import Sequence
from datetime import date

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.utils import date_range
from app.models.availability import RoomAvailability
from app.models.room import ExchangeRate, RoomCategory
from app.models.sanatorium import Sanatorium, SanatoriumStatus
from app.models.user import User, UserRole
from app.schemas.exchange_rate import ExchangeRateUpsert
from app.schemas.room import AvailabilityBulkCreate, RoomCategoryCreate, RoomCategoryUpdate
from app.core.pricing import enrich_room

_USD_UZS = "USD_UZS"


class RoomService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── rooms ──────────────────────────────────────────────────────────────

    async def get_by_id(self, room_id: uuid.UUID) -> RoomCategory | None:
        stmt = select(RoomCategory).where(RoomCategory.id == room_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def list_for_sanatorium(
        self,
        sanatorium_id: uuid.UUID,
        *,
        user: User | None,
        limit: int,
        offset: int,
        active_only: bool = True,
    ) -> tuple[Sequence[RoomCategory], int]:
        base = (
            select(RoomCategory)
            .join(Sanatorium, RoomCategory.sanatorium_id == Sanatorium.id)
            .where(RoomCategory.sanatorium_id == sanatorium_id)
        )
        if active_only:
            base = base.where(RoomCategory.is_active.is_(True))

        if user is None or user.role in (UserRole.CUSTOMER, UserRole.AGENT):
            base = base.where(Sanatorium.status == SanatoriumStatus.APPROVED)
        elif user.role == UserRole.ADMIN:
            base = base.where(Sanatorium.admin_user_id == user.id)

        total = (
            await self.db.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()

        stmt = base.order_by(RoomCategory.created_at.asc()).limit(limit).offset(offset)
        rows = (await self.db.execute(stmt)).scalars().all()
        return rows, total

    async def create(self, payload: RoomCategoryCreate, user: User) -> RoomCategory:
        sanatorium = await self._load_sanatorium_for_admin(
            payload.sanatorium_id, user
        )
        if sanatorium is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Sanatorium not found or not accessible",
            )

        room = RoomCategory(
            sanatorium_id=payload.sanatorium_id,
            name=payload.name.model_dump(exclude_none=True),
            room_amenities=payload.room_amenities,
            capacity=payload.capacity,
            base_price=payload.base_price,
            base_price_weekend=payload.base_price_weekend,
            base_currency=payload.base_currency,
            min_nights=payload.min_nights,
        )
        self.db.add(room)
        await self.db.commit()
        await self.db.refresh(room)
        return room

    async def update(
        self, room: RoomCategory, payload: RoomCategoryUpdate, user: User
    ) -> RoomCategory:
        data = payload.model_dump(exclude_unset=True)

        if "markup_percent" in data and user.role != UserRole.SUPER_ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only super_admin can change markup_percent",
            )

        if "name" in data and data["name"] is not None:
            data["name"] = {k: v for k, v in data["name"].items() if v is not None}

        for field, value in data.items():
            setattr(room, field, value)

        await self.db.commit()
        await self.db.refresh(room)
        return room

    async def _load_sanatorium_for_admin(
        self, sanatorium_id: uuid.UUID, user: User
    ) -> Sanatorium | None:
        stmt = select(Sanatorium).where(Sanatorium.id == sanatorium_id)
        sanatorium = (await self.db.execute(stmt)).scalar_one_or_none()
        if sanatorium is None:
            return None
        if user.role == UserRole.SUPER_ADMIN:
            return sanatorium
        if user.role == UserRole.ADMIN and sanatorium.admin_user_id == user.id:
            return sanatorium
        return None

    async def get_sanatorium_for_room(self, room: RoomCategory) -> Sanatorium | None:
        stmt = select(Sanatorium).where(Sanatorium.id == room.sanatorium_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    # ── availability ───────────────────────────────────────────────────────

    async def bulk_create_availability(
        self,
        room: RoomCategory,
        payload: AvailabilityBulkCreate,
        user: User,
    ) -> list[RoomAvailability]:
        if payload.date_from >= payload.date_to:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="date_from must be before date_to",
            )

        sanatorium = await self._load_sanatorium_for_admin(room.sanatorium_id, user)
        if sanatorium is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not allowed to manage this room's availability",
            )

        all_dates = date_range(payload.date_from, payload.date_to)

        existing_stmt = select(RoomAvailability).where(
            RoomAvailability.room_category_id == room.id,
            RoomAvailability.date.in_(all_dates),
        )
        existing_rows = {
            r.date: r
            for r in (await self.db.execute(existing_stmt)).scalars().all()
        }

        result: list[RoomAvailability] = []
        for d in all_dates:
            if d in existing_rows:
                if payload.overwrite:
                    row = existing_rows[d]
                    row.units_total = payload.units_total
                    row.units_available = payload.units_total
                    result.append(row)
            else:
                row = RoomAvailability(
                    room_category_id=room.id,
                    date=d,
                    units_total=payload.units_total,
                    units_available=payload.units_total,
                )
                self.db.add(row)
                result.append(row)

        await self.db.commit()
        for row in result:
            await self.db.refresh(row)
        return result

    async def get_availability(
        self,
        room: RoomCategory,
        date_from: date,
        date_to: date,
    ) -> list[RoomAvailability]:
        stmt = (
            select(RoomAvailability)
            .where(
                RoomAvailability.room_category_id == room.id,
                RoomAvailability.date >= date_from,
                RoomAvailability.date < date_to,
            )
            .order_by(RoomAvailability.date.asc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    # ── exchange rates ─────────────────────────────────────────────────────

    async def get_exchange_rate(self, pair: str) -> ExchangeRate | None:
        stmt = select(ExchangeRate).where(ExchangeRate.pair == pair)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def upsert_exchange_rate(self, payload: ExchangeRateUpsert) -> ExchangeRate:
        existing = await self.get_exchange_rate(payload.pair)
        if existing:
            existing.rate = payload.rate
            existing.valid_from = payload.valid_from
            await self.db.commit()
            await self.db.refresh(existing)
            return existing

        rate = ExchangeRate(
            pair=payload.pair,
            rate=payload.rate,
            valid_from=payload.valid_from,
        )
        self.db.add(rate)
        await self.db.commit()
        await self.db.refresh(rate)
        return rate

    async def list_exchange_rates(self) -> list[ExchangeRate]:
        stmt = select(ExchangeRate).order_by(ExchangeRate.pair.asc())
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_usd_uzs_rate(self) -> ExchangeRate | None:
        return await self.get_exchange_rate(_USD_UZS)

    # ── pricing helper ─────────────────────────────────────────────────────

    async def enrich(self, room: RoomCategory) -> dict:
        rate = await self.get_usd_uzs_rate()
        return enrich_room(room, rate)

    # ── search ─────────────────────────────────────────────────────────────

    async def search(
        self,
        *,
        check_in: date,
        check_out: date,
        guests: int,
        sanatorium_id: uuid.UUID | None = None,
    ) -> list[tuple[RoomCategory, dict]]:
        nights = (check_out - check_in).days
        if nights <= 0:
            return []

        all_dates = date_range(check_in, check_out)

        avail_subq = (
            select(
                RoomAvailability.room_category_id,
                func.count().label("covered_dates"),
            )
            .where(
                RoomAvailability.date.in_(all_dates),
                RoomAvailability.units_available >= 1,
            )
            .group_by(RoomAvailability.room_category_id)
            .subquery()
        )

        stmt = (
            select(RoomCategory)
            .join(Sanatorium, RoomCategory.sanatorium_id == Sanatorium.id)
            .join(avail_subq, RoomCategory.id == avail_subq.c.room_category_id)
            .where(
                Sanatorium.status == SanatoriumStatus.APPROVED,
                RoomCategory.is_active.is_(True),
                RoomCategory.capacity >= guests,
                RoomCategory.min_nights <= nights,
                avail_subq.c.covered_dates == nights,
            )
        )

        if sanatorium_id is not None:
            stmt = stmt.where(RoomCategory.sanatorium_id == sanatorium_id)

        rows = (await self.db.execute(stmt.order_by(RoomCategory.base_price.asc()))).scalars().all()
        rate = await self.get_usd_uzs_rate()
        return [(room, enrich_room(room, rate)) for room in rows]


def get_room_service(db: AsyncSession = Depends(get_db)) -> RoomService:
    return RoomService(db)
