from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.pricing import calculate_stay_total, convert_to_usd
from app.core.utils import date_range, pick_locale
from app.models.availability import RoomAvailability
from app.models.destination import Destination
from app.models.region import Region
from app.models.room import Room
from app.models.sanatorium import Sanatorium, SanatoriumImage, SanatoriumStatus
from app.schemas.search import StaySearchItem
from app.services.exchange_rate_service import (
    ExchangeRateService,
    get_exchange_rate_service,
)


@dataclass(slots=True)
class _Candidate:
    room: Room
    sanatorium: Sanatorium
    destination: Destination | None
    region: Region | None


@dataclass(slots=True)
class _SearchContext:
    locale: str
    check_in: date
    check_out: date
    nights: int
    adults: int
    children: int
    guests: int
    dates: list[date]


class SearchService:
    def __init__(self, db: AsyncSession, rates: ExchangeRateService) -> None:
        self.db = db
        self.rates = rates

    async def search_stays(
        self,
        *,
        locale: str,
        check_in: date,
        check_out: date,
        adults: int,
        children: int,
        limit: int,
        offset: int,
        location: str | None = None,
        sanatorium_id: uuid.UUID | None = None,
        destination_id: uuid.UUID | None = None,
        treatment_focus: str | None = None,
    ) -> tuple[list[StaySearchItem], int]:
        nights = (check_out - check_in).days
        if nights <= 0:
            return [], 0

        context = _SearchContext(
            locale=locale,
            check_in=check_in,
            check_out=check_out,
            nights=nights,
            adults=adults,
            children=children,
            guests=adults + children,
            dates=list(date_range(check_in, check_out)),
        )
        candidates = await self._find_candidates(
            nights=nights,
            guests=context.guests,
            location=location,
            sanatorium_id=sanatorium_id,
            destination_id=destination_id,
            treatment_focus=treatment_focus,
        )
        if not candidates:
            return [], 0

        available_items = await self._available_items(context, candidates)
        items = self._cheapest_by_sanatorium(available_items)
        items.sort(
            key=lambda item: (
                *self._comparison_price(item),
                -(item.avg_rating or Decimal("0")),
                item.sanatorium_name.lower(),
            )
        )
        total = len(items)
        return items[offset : offset + limit], total

    async def _find_candidates(
        self,
        *,
        nights: int,
        guests: int,
        location: str | None,
        sanatorium_id: uuid.UUID | None,
        destination_id: uuid.UUID | None,
        treatment_focus: str | None,
    ) -> list[_Candidate]:
        stmt = self._candidate_statement(
            nights=nights,
            guests=guests,
            location=location,
            sanatorium_id=sanatorium_id,
            destination_id=destination_id,
            treatment_focus=treatment_focus,
        )
        rows = (await self.db.execute(stmt)).all()
        return [
            _Candidate(
                room=row[0],
                sanatorium=row[1],
                destination=row[2],
                region=row[3],
            )
            for row in rows
        ]

    def _candidate_statement(
        self,
        *,
        nights: int,
        guests: int,
        location: str | None,
        sanatorium_id: uuid.UUID | None,
        destination_id: uuid.UUID | None,
        treatment_focus: str | None,
    ):
        stmt = (
            select(Room, Sanatorium, Destination, Region)
            .join(Sanatorium, Room.sanatorium_id == Sanatorium.id)
            .outerjoin(Destination, Sanatorium.destination_id == Destination.id)
            .outerjoin(Region, Sanatorium.region_id == Region.id)
            .where(
                Sanatorium.status == SanatoriumStatus.APPROVED,
                Room.is_active.is_(True),
                Room.inventory_count >= 1,
                Room.capacity >= 1,
                Room.min_nights <= nights,
                Room.capacity * Room.inventory_count >= guests,
            )
            .options(
                selectinload(Room.price_periods),
                selectinload(Sanatorium.images),
            )
            .order_by(Room.base_price.asc(), Sanatorium.created_at.asc())
        )
        if sanatorium_id is not None:
            stmt = stmt.where(Sanatorium.id == sanatorium_id)
        if destination_id is not None:
            stmt = stmt.where(Sanatorium.destination_id == destination_id)
        if treatment_focus:
            stmt = stmt.where(Sanatorium.treatment_focuses.contains([treatment_focus]))
        if location and location.strip():
            stmt = stmt.where(_location_clause(location.strip()))
        return stmt

    async def _available_items(
        self, context: _SearchContext, candidates: list[_Candidate]
    ) -> list[StaySearchItem]:
        max_used_by_room = await self._max_used_by_room(
            room_ids=[candidate.room.id for candidate in candidates],
            dates=context.dates,
        )
        rate = await self.rates.get_usd_uzs()
        items: list[StaySearchItem] = []
        for candidate in candidates:
            item = self._candidate_item(candidate, context, max_used_by_room, rate)
            if item is not None:
                items.append(item)
        return items

    def _candidate_item(
        self,
        candidate: _Candidate,
        context: _SearchContext,
        max_used_by_room: dict[uuid.UUID, int],
        rate,
    ) -> StaySearchItem | None:
        room = candidate.room
        rooms_needed = math.ceil(context.guests / room.capacity)
        free_worst_case = max(
            room.inventory_count - max_used_by_room.get(room.id, 0),
            0,
        )
        if rooms_needed > free_worst_case:
            return None

        total = calculate_stay_total(room, context.dates, room.price_periods)
        total = (total * rooms_needed).quantize(Decimal("0.01"))
        total_usd = convert_to_usd(total, room.base_currency, rate)
        return self._to_item(
            candidate,
            context=context,
            room=room,
            rooms_needed=rooms_needed,
            total=total,
            total_usd=total_usd,
        )

    async def _max_used_by_room(
        self, *, room_ids: list[uuid.UUID], dates: list[date]
    ) -> dict[uuid.UUID, int]:
        usage_rows = (
            await self.db.execute(
                select(
                    RoomAvailability.room_id,
                    func.max(
                        RoomAvailability.units_blocked + RoomAvailability.units_booked
                    ).label("max_used"),
                )
                .where(
                    RoomAvailability.room_id.in_(room_ids),
                    RoomAvailability.date.in_(dates),
                )
                .group_by(RoomAvailability.room_id)
            )
        ).all()
        return {row.room_id: int(row.max_used) for row in usage_rows}

    def _to_item(
        self,
        candidate: _Candidate,
        *,
        context: _SearchContext,
        room: Room,
        rooms_needed: int,
        total: Decimal,
        total_usd: Decimal | None,
    ) -> StaySearchItem:
        sanatorium = candidate.sanatorium
        return StaySearchItem(
            sanatorium_id=sanatorium.id,
            sanatorium_slug=sanatorium.slug,
            sanatorium_name=pick_locale(sanatorium.name, context.locale),
            city=sanatorium.city,
            region_id=sanatorium.region_id,
            region_name=pick_locale(candidate.region.name, context.locale)
            if candidate.region
            else None,
            destination_id=sanatorium.destination_id,
            destination_name=pick_locale(candidate.destination.name, context.locale)
            if candidate.destination
            else None,
            primary_image_url=_primary_image_url(sanatorium.images),
            stars=sanatorium.stars,
            avg_rating=sanatorium.avg_rating,
            review_count=sanatorium.review_count,
            property_type=sanatorium.property_type,
            wellness_category=sanatorium.wellness_category,
            treatment_focuses=sanatorium.treatment_focuses,
            check_in=context.check_in,
            check_out=context.check_out,
            nights=context.nights,
            adults=context.adults,
            children=context.children,
            guests=context.guests,
            available_room_id=room.id,
            available_room_name=pick_locale(room.name, context.locale),
            rooms_count_needed=rooms_needed,
            min_total_price=total,
            min_total_price_currency=room.base_currency,
            min_total_price_usd=total_usd,
        )

    def _cheapest_by_sanatorium(
        self, items: list[StaySearchItem]
    ) -> list[StaySearchItem]:
        best_by_sanatorium: dict[uuid.UUID, StaySearchItem] = {}
        for item in items:
            current = best_by_sanatorium.get(item.sanatorium_id)
            if current is None or self._is_cheaper(item, current):
                best_by_sanatorium[item.sanatorium_id] = item
        return list(best_by_sanatorium.values())

    def _is_cheaper(self, candidate: StaySearchItem, current: StaySearchItem) -> bool:
        return self._comparison_price(candidate) < self._comparison_price(current)

    def _comparison_price(self, item: StaySearchItem) -> tuple[bool, Decimal]:
        return (
            item.min_total_price_usd is None,
            item.min_total_price_usd or item.min_total_price,
        )


def _primary_image_url(images: list[SanatoriumImage]) -> str | None:
    if not images:
        return None
    primary = next((image for image in images if image.is_primary), None)
    return (primary or images[0]).url


def _location_clause(term: str):
    return (
        Sanatorium.name["uz"].astext.icontains(term, autoescape=True)
        | Sanatorium.name["ru"].astext.icontains(term, autoescape=True)
        | Sanatorium.name["en"].astext.icontains(term, autoescape=True)
        | Sanatorium.city.icontains(term, autoescape=True)
        | Sanatorium.slug.icontains(term, autoescape=True)
        | Destination.slug.icontains(term, autoescape=True)
        | Destination.name["uz"].astext.icontains(term, autoescape=True)
        | Destination.name["ru"].astext.icontains(term, autoescape=True)
        | Destination.name["en"].astext.icontains(term, autoescape=True)
        | Region.slug.icontains(term, autoescape=True)
        | Region.name["uz"].astext.icontains(term, autoescape=True)
        | Region.name["ru"].astext.icontains(term, autoescape=True)
        | Region.name["en"].astext.icontains(term, autoescape=True)
    )


def get_search_service(
    db: AsyncSession = Depends(get_db),
    rates: ExchangeRateService = Depends(get_exchange_rate_service),
) -> SearchService:
    return SearchService(db, rates)
