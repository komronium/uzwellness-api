from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.currency import CurrencyConverter
from app.core.database import get_db
from app.core.utils import date_range, pick_locale
from app.models.amenity import RoomAmenity
from app.models.program import (
    TreatmentProgram,
    TreatmentProgramType,
    TreatmentStayPackageKind,
)
from app.models.rate_plan import BoardType, RatePlan
from app.models.room import Room, RoomImage
from app.models.sanatorium import Sanatorium, SanatoriumStatus
from app.models.stay_option import SanatoriumStayOptionPrice, StayOptionGuestType
from app.schemas.room_offer import (
    RoomOfferAlternativeDate,
    RoomOfferCard,
    RoomOfferGuestInclusions,
    RoomOfferInclusion,
    RoomOfferPackageKind,
    RoomOfferPhoto,
    RoomOfferPrice,
    RoomOfferRequestedRoom,
    RoomOfferSearchRequest,
    RoomOfferSearchResponse,
    RoomOfferSort,
    RoomOfferTreatmentGroup,
    RoomOfferTreatmentOption,
)
from app.services.availability_usage import max_used_by_room
from app.services.exchange_rate_service import (
    ExchangeRateService,
    get_exchange_rate_service,
)
from app.services.room_offer_guests import (
    GuestKey,
    GuestStayChoice,
    guest_option,
    guest_options,
    guests,
    program_kind,
    programs_for_guest,
    resolve_guest_program,
    selected_treatments,
)
from app.services.room_offer_pricing import (
    CENTS,
    ZERO,
    apply_promo,
    original_total,
    room_total,
    stay_option_total,
    treatment_total,
)


@dataclass(slots=True)
class _OfferContext:
    locale: str
    sanatorium_id: uuid.UUID
    check_in: date
    check_out: date
    nights: int
    dates: list[date]
    requested_rooms: list[RoomOfferRequestedRoom]
    guest_options: dict[GuestKey, GuestStayChoice]
    treatment_by_guest: dict[GuestKey, TreatmentProgram]
    treatments: list[TreatmentProgram]
    stay_option_prices: dict[
        tuple[StayOptionGuestType, BoardType, bool], SanatoriumStayOptionPrice
    ]
    converter: CurrencyConverter


class RoomOfferService:
    def __init__(self, db: AsyncSession, rates: ExchangeRateService) -> None:
        self.db = db
        self.rates = rates

    async def search(
        self,
        *,
        sanatorium_id: uuid.UUID,
        payload: RoomOfferSearchRequest,
        locale: str,
        display_currency: str = "UZS",
    ) -> RoomOfferSearchResponse:
        sanatorium = await self.db.get(Sanatorium, sanatorium_id)
        if sanatorium is None or sanatorium.status != SanatoriumStatus.APPROVED:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sanatorium not found",
            )

        context = await self._context(
            sanatorium_id=sanatorium_id,
            payload=payload,
            locale=locale,
            display_currency=display_currency,
        )
        rooms = await self._rooms(sanatorium_id=sanatorium_id, payload=payload)
        usage = await max_used_by_room(
            self.db,
            room_ids=[room.id for room in rooms],
            dates=context.dates,
        )
        treatment_selection = self._treatment_selection(context)
        offers = self._offers(context, rooms, usage)
        offers = self._filter_by_price(offers, payload)
        offers.sort(
            key=_offer_display_total,
            reverse=payload.sort == RoomOfferSort.HIGHEST_PRICE,
        )
        alternatives = []
        if not offers:
            alternatives = await self._alternatives(context, rooms)

        return RoomOfferSearchResponse(
            sanatorium_id=sanatorium_id,
            check_in=payload.check_in,
            check_out=payload.check_out,
            nights=context.nights,
            rooms_count=len(payload.rooms),
            adults=sum(room.adults for room in payload.rooms),
            children=sum(len(room.children) for room in payload.rooms),
            guests=sum(room.guests_count for room in payload.rooms),
            available_count=len(offers),
            treatment_selection=treatment_selection,
            offers=offers,
            alternatives=alternatives,
        )

    async def _context(
        self,
        *,
        sanatorium_id: uuid.UUID,
        payload: RoomOfferSearchRequest,
        locale: str,
        display_currency: str,
    ) -> _OfferContext:
        nights = (payload.check_out - payload.check_in).days
        treatments = await self._treatments(
            sanatorium_id=sanatorium_id,
            nights=nights,
        )
        stay_option_prices = await self._stay_option_prices(sanatorium_id)
        options = guest_options(payload)
        selected = selected_treatments(payload, treatments, options)
        return _OfferContext(
            locale=locale,
            sanatorium_id=sanatorium_id,
            check_in=payload.check_in,
            check_out=payload.check_out,
            nights=nights,
            dates=list(date_range(payload.check_in, payload.check_out)),
            requested_rooms=payload.rooms,
            guest_options=options,
            treatment_by_guest=selected,
            treatments=treatments,
            stay_option_prices=stay_option_prices,
            converter=await self.rates.get_converter(display_currency),
        )

    async def _rooms(
        self, *, sanatorium_id: uuid.UUID, payload: RoomOfferSearchRequest
    ) -> list[Room]:
        stmt = (
            select(Room)
            .where(
                Room.sanatorium_id == sanatorium_id,
                Room.is_active.is_(True),
                Room.deleted_at.is_(None),
            )
            .options(
                selectinload(Room.price_periods),
                selectinload(Room.images),
                selectinload(Room.amenity_links).selectinload(RoomAmenity.amenity),
                selectinload(Room.amenities),
                selectinload(Room.rate_plans).selectinload(RatePlan.date_rules),
            )
            .order_by(Room.display_order.asc(), Room.base_price.asc())
        )
        if payload.filters.room_type_ids:
            stmt = stmt.where(Room.id.in_(payload.filters.room_type_ids))
        rooms = list((await self.db.scalars(stmt)).all())
        if not payload.filters.amenity_ids:
            return rooms
        requested = set(payload.filters.amenity_ids)
        return [
            room
            for room in rooms
            if requested.issubset({amenity.id for amenity in room.amenities})
        ]

    async def _treatments(
        self, *, sanatorium_id: uuid.UUID, nights: int
    ) -> list[TreatmentProgram]:
        stmt = (
            select(TreatmentProgram)
            .where(
                TreatmentProgram.sanatorium_id == sanatorium_id,
                TreatmentProgram.is_active.is_(True),
                TreatmentProgram.program_type == TreatmentProgramType.STAY_PACKAGE,
            )
            .order_by(
                TreatmentProgram.is_default_stay_package.desc(),
                TreatmentProgram.display_order.asc(),
                TreatmentProgram.created_at.asc(),
            )
        )
        programs = list((await self.db.scalars(stmt)).all())
        return [
            program
            for program in programs
            if (program.min_nights is None or nights >= program.min_nights)
            and (program.max_nights is None or nights <= program.max_nights)
        ]

    async def _stay_option_prices(
        self, sanatorium_id: uuid.UUID
    ) -> dict[tuple[StayOptionGuestType, BoardType, bool], SanatoriumStayOptionPrice]:
        rows = list(
            (
                await self.db.scalars(
                    select(SanatoriumStayOptionPrice).where(
                        SanatoriumStayOptionPrice.sanatorium_id == sanatorium_id
                    )
                )
            ).all()
        )
        return {
            (row.guest_type, row.board, row.treatment_included): row for row in rows
        }

    def _offers(
        self,
        context: _OfferContext,
        rooms: list[Room],
        usage: dict[uuid.UUID, int],
    ) -> list[RoomOfferCard]:
        offers: list[RoomOfferCard] = []
        for room in rooms:
            available_rooms = self._available_rooms(room, usage)
            if not self._room_fits_request(context, room, available_rooms):
                continue
            rate_plans = [rp for rp in room.rate_plans if rp.is_active] or [None]
            for rate_plan in rate_plans:
                if rate_plan is not None and not self._rate_plan_fits(
                    rate_plan, context
                ):
                    continue
                offers.append(
                    self._offer(
                        context=context,
                        room=room,
                        rate_plan=rate_plan,
                        available_rooms=available_rooms,
                    )
                )
        return offers

    @staticmethod
    def _available_rooms(room: Room, usage: dict[uuid.UUID, int]) -> int:
        return max(room.inventory_count - usage.get(room.id, 0), 0)

    def _room_fits_request(
        self, context: _OfferContext, room: Room, available_rooms: int
    ) -> bool:
        if context.nights < room.min_nights:
            return False
        if len(context.requested_rooms) > available_rooms:
            return False
        for requested in context.requested_rooms:
            if requested.guests_count > room.capacity:
                return False
            if room.max_adults is not None and requested.adults > room.max_adults:
                return False
            if (
                room.max_children is not None
                and len(requested.children) > room.max_children
            ):
                return False
        return True

    def _rate_plan_fits(self, rate_plan: RatePlan, context: _OfferContext) -> bool:
        if not self._rate_plan_matches_requested_room_boards(rate_plan, context):
            return False
        if rate_plan.min_nights is not None and context.nights < rate_plan.min_nights:
            return False
        if rate_plan.max_nights is not None and context.nights > rate_plan.max_nights:
            return False
        rules = {rule.date: rule for rule in rate_plan.date_rules}
        for target in context.dates:
            rule = rules.get(target)
            if rule is None:
                continue
            if rule.is_closed is True:
                return False
            if (
                rule.min_stay_nights is not None
                and context.nights < rule.min_stay_nights
            ):
                return False
        arrival_rule = rules.get(context.dates[0]) if context.dates else None
        return (
            arrival_rule is None
            or arrival_rule.min_stay_arrival_nights is None
            or context.nights >= arrival_rule.min_stay_arrival_nights
        )

    @staticmethod
    def _rate_plan_matches_requested_room_boards(
        rate_plan: RatePlan, context: _OfferContext
    ) -> bool:
        return all(room.board == rate_plan.board for room in context.requested_rooms)

    def _offer(
        self,
        *,
        context: _OfferContext,
        room: Room,
        rate_plan: RatePlan | None,
        available_rooms: int,
    ) -> RoomOfferCard:
        subtotal = (
            room_total(room, rate_plan, context.dates, len(context.requested_rooms))
            + stay_option_total(
                prices=context.stay_option_prices,
                requested_rooms=context.requested_rooms,
                options=context.guest_options,
                nights=context.nights,
                converter=context.converter,
                currency=room.base_currency,
            )
            + treatment_total(
                requested_rooms=context.requested_rooms,
                options=context.guest_options,
                treatments=context.treatments,
                treatment_by_guest=context.treatment_by_guest,
                converter=context.converter,
                currency=room.base_currency,
            )
        ).quantize(CENTS, ROUND_HALF_UP)
        total = apply_promo(subtotal, rate_plan)
        return RoomOfferCard(
            offer_id=f"{room.id}:{rate_plan.id if rate_plan else 'base'}",
            room_id=room.id,
            rate_plan_id=rate_plan.id if rate_plan else None,
            room_name=pick_locale(room.name, context.locale),
            rate_plan_name=pick_locale(rate_plan.name, context.locale)
            if rate_plan
            else None,
            capacity=room.capacity,
            max_adults=room.max_adults,
            max_children=room.max_children,
            available_rooms=available_rooms,
            photo_count=len(room.images),
            photos=[self._photo(image, context.locale) for image in room.images[:8]],
            price=RoomOfferPrice(
                total=total,
                original_total=original_total(subtotal, rate_plan),
                currency=room.base_currency,
                display_total=context.converter.convert(total, room.base_currency),
                display_currency=context.converter.target,
                rooms_count=len(context.requested_rooms),
                adults=sum(room.adults for room in context.requested_rooms),
                children=sum(len(room.children) for room in context.requested_rooms),
                guests=sum(room.guests_count for room in context.requested_rooms),
                min_stay_nights=rate_plan.min_nights if rate_plan else room.min_nights,
                payment_timing=rate_plan.payment_timing if rate_plan else None,
                confirmation=rate_plan.confirmation if rate_plan else None,
                refundable=rate_plan.refundable if rate_plan else None,
                free_cancellation_days=rate_plan.free_cancellation_days
                if rate_plan
                else None,
                cancellation_penalty_percent=rate_plan.cancellation_penalty_percent
                if rate_plan
                else None,
                cancellation_penalty_amount=rate_plan.cancellation_penalty_amount
                if rate_plan
                else None,
            ),
            inclusions=self._inclusions(context),
        )

    def _treatment_selection(
        self, context: _OfferContext
    ) -> list[RoomOfferTreatmentGroup]:
        groups: list[RoomOfferTreatmentGroup] = []
        for room_index, requested_room in enumerate(context.requested_rooms):
            for guest in guests(requested_room):
                option = guest_option(
                    context.guest_options, room_index, guest.guest_index
                )
                package_kind = RoomOfferPackageKind(option.package_kind.value)
                programs = programs_for_guest(
                    context.treatments,
                    guest,
                    program_kind(option),
                )
                default = programs[0] if programs else None
                selected = context.treatment_by_guest.get(
                    (room_index, guest.guest_index), default
                )
                selected_price = selected.price if selected and selected.price else ZERO
                # Deltas already assume one currency per group; reuse it for display.
                group_currency = next(
                    (program.currency for program in programs if program.currency), None
                )
                groups.append(
                    RoomOfferTreatmentGroup(
                        room_index=room_index,
                        guest=guest,
                        board=option.board,
                        package_kind=package_kind,
                        selected_program_id=selected.id if selected else None,
                        options=[
                            self._treatment_option(
                                program, selected_price, group_currency, context
                            )
                            for program in programs
                        ],
                    )
                )
        return groups

    def _treatment_option(
        self,
        program: TreatmentProgram,
        selected_price: Decimal,
        group_currency: str | None,
        context: _OfferContext,
    ) -> RoomOfferTreatmentOption:
        price = program.price or ZERO
        price_delta = (price - selected_price).quantize(CENTS, ROUND_HALF_UP)
        display_price_delta = (
            context.converter.convert(price_delta, group_currency)
            if group_currency
            else None
        )
        return RoomOfferTreatmentOption(
            id=program.id,
            package_kind=RoomOfferPackageKind(program.stay_package_kind.value),
            name=pick_locale(program.name, context.locale),
            description=pick_locale(program.description, context.locale) or None,
            duration_minutes=program.duration_minutes,
            medical_exam_count=program.medical_exam_count,
            medical_procedure_count=program.medical_procedure_count,
            drink_cure_included=program.drink_cure_included,
            sauna_entries=program.sauna_entries,
            pool_access_included=program.pool_access_included,
            included_services=program.included_services,
            price=program.price,
            currency=program.currency,
            price_delta=price_delta,
            display_price=(
                context.converter.convert(program.price, group_currency)
                if group_currency and program.price is not None
                else None
            ),
            display_price_delta=display_price_delta,
            display_currency=(
                context.converter.target if display_price_delta is not None else None
            ),
        )

    def _inclusions(self, context: _OfferContext) -> list[RoomOfferGuestInclusions]:
        rows: list[RoomOfferGuestInclusions] = []
        for room_index, requested_room in enumerate(context.requested_rooms):
            for guest in guests(requested_room):
                option = guest_option(
                    context.guest_options, room_index, guest.guest_index
                )
                program = resolve_guest_program(
                    context.treatments,
                    context.treatment_by_guest,
                    room_index,
                    guest,
                    option,
                )
                items = [self._accommodation_inclusion(context, option.board)]
                if program is not None:
                    package_type = (
                        "treatment"
                        if program.stay_package_kind
                        == TreatmentStayPackageKind.TREATMENT
                        else "special_package"
                    )
                    items.append(
                        RoomOfferInclusion(
                            type=package_type,
                            title=pick_locale(program.name, context.locale),
                            description=pick_locale(program.description, context.locale)
                            or None,
                        )
                    )
                rows.append(
                    RoomOfferGuestInclusions(
                        room_index=room_index,
                        guest=guest,
                        items=items,
                    )
                )
        return rows

    def _accommodation_inclusion(
        self, context: _OfferContext, board: BoardType
    ) -> RoomOfferInclusion:
        return RoomOfferInclusion(
            type="accommodation",
            title="Accommodation",
            description=f"{context.nights} night(s), {self._board_label(board)}",
        )

    @staticmethod
    def _board_label(board: BoardType) -> str:
        labels = {
            BoardType.ROOM_ONLY: "room only",
            BoardType.BREAKFAST: "breakfast",
            BoardType.HALF_BOARD: "2 meals a day",
            BoardType.FULL_BOARD: "3 meals a day",
            BoardType.ALL_INCLUSIVE: "all inclusive",
        }
        return labels[board]

    @staticmethod
    def _photo(image: RoomImage, locale: str) -> RoomOfferPhoto:
        return RoomOfferPhoto(
            id=image.id,
            url=image.url,
            is_primary=image.is_primary,
            order=image.order,
            caption=pick_locale(image.caption_i18n, locale) or image.caption,
        )

    @staticmethod
    def _filter_by_price(
        offers: list[RoomOfferCard], payload: RoomOfferSearchRequest
    ) -> list[RoomOfferCard]:
        result = offers
        if payload.filters.price_min is not None:
            result = [
                offer
                for offer in result
                if _offer_display_total(offer) >= payload.filters.price_min
            ]
        if payload.filters.price_max is not None:
            result = [
                offer
                for offer in result
                if _offer_display_total(offer) <= payload.filters.price_max
            ]
        return result

    async def _alternatives(
        self, context: _OfferContext, rooms: list[Room]
    ) -> list[RoomOfferAlternativeDate]:
        alternatives: list[RoomOfferAlternativeDate] = []
        for delta in range(1, 91):
            check_in = context.check_in + timedelta(days=delta)
            check_out = check_in + timedelta(days=context.nights)
            dates = list(date_range(check_in, check_out))
            usage = await max_used_by_room(
                self.db, room_ids=[room.id for room in rooms], dates=dates
            )
            cheapest = self._cheapest_alternative(context, rooms, usage, dates)
            if cheapest is None:
                continue
            alternatives.append(
                RoomOfferAlternativeDate(
                    check_in=check_in,
                    check_out=check_out,
                    nights=context.nights,
                    min_total_price=cheapest[0],
                    currency=cheapest[1],
                    display_min_total_price=context.converter.convert(
                        cheapest[0], cheapest[1]
                    ),
                    display_currency=context.converter.target,
                )
            )
            if len(alternatives) >= 4:
                break
        return alternatives

    def _cheapest_alternative(
        self,
        context: _OfferContext,
        rooms: list[Room],
        usage: dict[uuid.UUID, int],
        dates: list[date],
    ) -> tuple[Decimal, str] | None:
        cheapest: tuple[Decimal, str, Decimal] | None = None
        alt_context = _OfferContext(
            locale=context.locale,
            sanatorium_id=context.sanatorium_id,
            check_in=dates[0],
            check_out=dates[-1] + timedelta(days=1),
            nights=context.nights,
            dates=dates,
            requested_rooms=context.requested_rooms,
            guest_options=context.guest_options,
            treatment_by_guest=context.treatment_by_guest,
            treatments=context.treatments,
            stay_option_prices=context.stay_option_prices,
            converter=context.converter,
        )
        for room in rooms:
            available_rooms = self._available_rooms(room, usage)
            if not self._room_fits_request(alt_context, room, available_rooms):
                continue
            rate_plans = [rp for rp in room.rate_plans if rp.is_active] or [None]
            for rate_plan in rate_plans:
                if rate_plan is not None and not self._rate_plan_fits(
                    rate_plan, alt_context
                ):
                    continue
                offer = self._offer(
                    context=alt_context,
                    room=room,
                    rate_plan=rate_plan,
                    available_rooms=available_rooms,
                )
                total = offer.price.total
                display_total = _offer_display_total(offer)
                if cheapest is None or display_total < cheapest[2]:
                    cheapest = (total, room.base_currency, display_total)
        if cheapest is None:
            return None
        return cheapest[0], cheapest[1]


def _offer_display_total(offer: RoomOfferCard) -> Decimal:
    return offer.price.display_total or offer.price.total


def get_room_offer_service(
    db: AsyncSession = Depends(get_db),
    rates: ExchangeRateService = Depends(get_exchange_rate_service),
) -> RoomOfferService:
    return RoomOfferService(db, rates)
