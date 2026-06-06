from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.pricing import (
    calculate_rate_plan_night_price,
    calculate_stay_total,
    convert_to_usd,
    convert_to_uzs,
)
from app.core.utils import date_range, pick_locale
from app.models.amenity import RoomAmenity
from app.models.availability import RoomAvailability
from app.models.exchange_rate import ExchangeRate
from app.models.program import (
    TreatmentGuestApplicability,
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
    RoomOfferGuest,
    RoomOfferGuestInclusions,
    RoomOfferGuestOption,
    RoomOfferGuestType,
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
from app.services.exchange_rate_service import (
    ExchangeRateService,
    get_exchange_rate_service,
)

_CENTS = Decimal("0.01")
_ZERO = Decimal("0")


@dataclass(slots=True)
class _OfferContext:
    locale: str
    sanatorium_id: uuid.UUID
    check_in: date
    check_out: date
    nights: int
    dates: list[date]
    requested_rooms: list[RoomOfferRequestedRoom]
    guest_options: dict[tuple[int, int], RoomOfferGuestOption]
    treatment_by_guest: dict[tuple[int, int], TreatmentProgram]
    treatments: list[TreatmentProgram]
    stay_option_prices: dict[
        tuple[StayOptionGuestType, BoardType, bool], SanatoriumStayOptionPrice
    ]
    exchange_rate: ExchangeRate | None


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
        )
        rooms = await self._rooms(sanatorium_id=sanatorium_id, payload=payload)
        usage = await self._max_used_by_room(
            room_ids=[room.id for room in rooms],
            dates=context.dates,
        )
        treatment_selection = self._treatment_selection(context)
        offers = self._offers(context, rooms, usage)
        offers = self._filter_by_price(offers, payload)
        offers.sort(
            key=lambda offer: offer.price.total,
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
    ) -> _OfferContext:
        nights = (payload.check_out - payload.check_in).days
        treatments = await self._treatments(
            sanatorium_id=sanatorium_id,
            nights=nights,
        )
        stay_option_prices = await self._stay_option_prices(sanatorium_id)
        guest_options = self._guest_options(payload)
        selected = self._selected_treatments(
            payload=payload,
            treatments=treatments,
            guest_options=guest_options,
        )
        return _OfferContext(
            locale=locale,
            sanatorium_id=sanatorium_id,
            check_in=payload.check_in,
            check_out=payload.check_out,
            nights=nights,
            dates=list(date_range(payload.check_in, payload.check_out)),
            requested_rooms=payload.rooms,
            guest_options=guest_options,
            treatment_by_guest=selected,
            treatments=treatments,
            stay_option_prices=stay_option_prices,
            exchange_rate=await self.rates.get_usd_uzs(),
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
                selectinload(Room.rate_plans).selectinload(RatePlan.amenities),
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

    def _selected_treatments(
        self,
        *,
        payload: RoomOfferSearchRequest,
        treatments: list[TreatmentProgram],
        guest_options: dict[tuple[int, int], RoomOfferGuestOption],
    ) -> dict[tuple[int, int], TreatmentProgram]:
        by_id = {program.id: program for program in treatments}
        selected: dict[tuple[int, int], TreatmentProgram] = {}
        for item in payload.treatment_selections:
            program = by_id.get(item.program_id)
            if program is None:
                continue
            if item.room_index >= len(payload.rooms):
                continue
            if item.guest_index >= payload.rooms[item.room_index].guests_count:
                continue
            guest = self._guests(payload.rooms[item.room_index])[item.guest_index]
            option = guest_options.get(
                (item.room_index, item.guest_index),
                self._default_guest_option(item.room_index, item.guest_index),
            )
            if program not in self._programs_for_guest(
                [program], guest, self._program_kind(option)
            ):
                continue
            selected[(item.room_index, item.guest_index)] = program
        return selected

    async def _max_used_by_room(
        self, *, room_ids: list[uuid.UUID], dates: list[date]
    ) -> dict[uuid.UUID, int]:
        if not room_ids:
            return {}
        rows = (
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
        return {row.room_id: int(row.max_used or 0) for row in rows}

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
        if not self._rate_plan_matches_guest_boards(rate_plan, context):
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
    def _rate_plan_matches_guest_boards(
        rate_plan: RatePlan, context: _OfferContext
    ) -> bool:
        return all(
            option.board == rate_plan.board for option in context.guest_options.values()
        )

    def _offer(
        self,
        *,
        context: _OfferContext,
        room: Room,
        rate_plan: RatePlan | None,
        available_rooms: int,
    ) -> RoomOfferCard:
        room_total = self._room_total(context, room, rate_plan)
        stay_option_total = self._stay_option_total(context, room.base_currency)
        treatment_total = self._treatment_total(context, room.base_currency)
        subtotal = (room_total + stay_option_total + treatment_total).quantize(
            _CENTS, ROUND_HALF_UP
        )
        original_total = self._original_total(subtotal, rate_plan)
        total = self._apply_promo(subtotal, rate_plan)
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
                original_total=original_total,
                currency=room.base_currency,
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
            inclusions=self._inclusions(context, rate_plan),
        )

    def _room_total(
        self, context: _OfferContext, room: Room, rate_plan: RatePlan | None
    ) -> Decimal:
        if rate_plan is None:
            return (
                calculate_stay_total(room, context.dates, room.price_periods)
                * len(context.requested_rooms)
            ).quantize(_CENTS, ROUND_HALF_UP)
        rules = {rule.date: rule for rule in rate_plan.date_rules}
        total = _ZERO
        for target in context.dates:
            rule = rules.get(target)
            total += calculate_rate_plan_night_price(
                room,
                rate_plan,
                target,
                room.price_periods,
                selling_rate_override=rule.selling_rate if rule else None,
            )
        return (total * len(context.requested_rooms)).quantize(_CENTS, ROUND_HALF_UP)

    def _stay_option_total(self, context: _OfferContext, currency: str) -> Decimal:
        if not context.stay_option_prices:
            return _ZERO
        total = _ZERO
        for room_index, requested_room in enumerate(context.requested_rooms):
            for guest in self._guests(requested_room):
                option = self._guest_option(context, room_index, guest.guest_index)
                price = self._stay_option_price(context, guest, option)
                converted = self._convert(
                    price.price_delta, price.currency, currency, context
                )
                if converted is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Exchange rate is required for stay option pricing",
                    )
                total += converted * context.nights
        return total.quantize(_CENTS, ROUND_HALF_UP)

    def _stay_option_price(
        self,
        context: _OfferContext,
        guest: RoomOfferGuest,
        option: RoomOfferGuestOption,
    ) -> SanatoriumStayOptionPrice:
        guest_type = (
            StayOptionGuestType.ADULT
            if guest.type == RoomOfferGuestType.ADULT
            else StayOptionGuestType.CHILD
        )
        price = context.stay_option_prices.get(
            (guest_type, option.board, option.treatment_included)
        )
        if price is None or not price.is_available:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected stay option is not available",
            )
        return price

    def _treatment_total(self, context: _OfferContext, currency: str) -> Decimal:
        total = _ZERO
        for room_index, requested_room in enumerate(context.requested_rooms):
            for guest in self._guests(requested_room):
                option = self._guest_option(context, room_index, guest.guest_index)
                programs = self._programs_for_guest(
                    context.treatments,
                    guest,
                    self._program_kind(option),
                )
                default = programs[0] if programs else None
                program = context.treatment_by_guest.get(
                    (room_index, guest.guest_index), default
                )
                if program is None or program.price is None or program.currency is None:
                    continue
                converted = self._convert(
                    program.price, program.currency, currency, context
                )
                if converted is not None:
                    total += converted
        return total.quantize(_CENTS, ROUND_HALF_UP)

    @staticmethod
    def _convert(
        amount: Decimal,
        source_currency: str,
        target_currency: str,
        context: _OfferContext,
    ) -> Decimal | None:
        if source_currency == target_currency:
            return amount.quantize(_CENTS, ROUND_HALF_UP)
        if target_currency == "UZS":
            return convert_to_uzs(amount, source_currency, context.exchange_rate)
        if target_currency == "USD":
            return convert_to_usd(amount, source_currency, context.exchange_rate)
        return None

    @staticmethod
    def _original_total(
        subtotal: Decimal, rate_plan: RatePlan | None
    ) -> Decimal | None:
        if rate_plan is None or not rate_plan.promo_percent:
            return None
        return subtotal

    @staticmethod
    def _apply_promo(subtotal: Decimal, rate_plan: RatePlan | None) -> Decimal:
        if rate_plan is None or not rate_plan.promo_percent:
            return subtotal
        return (subtotal * (1 - rate_plan.promo_percent / 100)).quantize(
            _CENTS, ROUND_HALF_UP
        )

    def _treatment_selection(
        self, context: _OfferContext
    ) -> list[RoomOfferTreatmentGroup]:
        groups: list[RoomOfferTreatmentGroup] = []
        for room_index, requested_room in enumerate(context.requested_rooms):
            for guest in self._guests(requested_room):
                option = self._guest_option(context, room_index, guest.guest_index)
                package_kind = RoomOfferPackageKind(option.package_kind.value)
                programs = self._programs_for_guest(
                    context.treatments,
                    guest,
                    self._program_kind(option),
                )
                default = programs[0] if programs else None
                selected = context.treatment_by_guest.get(
                    (room_index, guest.guest_index), default
                )
                selected_price = (
                    selected.price if selected and selected.price else _ZERO
                )
                groups.append(
                    RoomOfferTreatmentGroup(
                        room_index=room_index,
                        guest=guest,
                        board=option.board,
                        package_kind=package_kind,
                        selected_program_id=selected.id if selected else None,
                        options=[
                            self._treatment_option(program, selected_price, context)
                            for program in programs
                        ],
                    )
                )
        return groups

    def _treatment_option(
        self,
        program: TreatmentProgram,
        selected_price: Decimal,
        context: _OfferContext,
    ) -> RoomOfferTreatmentOption:
        price = program.price or _ZERO
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
            price_delta=(price - selected_price).quantize(_CENTS, ROUND_HALF_UP),
        )

    def _inclusions(
        self, context: _OfferContext, rate_plan: RatePlan | None
    ) -> list[RoomOfferGuestInclusions]:
        rows: list[RoomOfferGuestInclusions] = []
        for room_index, requested_room in enumerate(context.requested_rooms):
            for guest in self._guests(requested_room):
                option = self._guest_option(context, room_index, guest.guest_index)
                programs = self._programs_for_guest(
                    context.treatments,
                    guest,
                    self._program_kind(option),
                )
                default = programs[0] if programs else None
                program = context.treatment_by_guest.get(
                    (room_index, guest.guest_index), default
                )
                items = [self._accommodation_inclusion(context, option.board)]
                if rate_plan is not None:
                    items.extend(self._rate_plan_service_inclusions(rate_plan, context))
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
    def _rate_plan_service_inclusions(
        rate_plan: RatePlan, context: _OfferContext
    ) -> list[RoomOfferInclusion]:
        return [
            RoomOfferInclusion(
                type="service",
                title=pick_locale(amenity.name, context.locale),
                description=pick_locale(amenity.description, context.locale) or None,
            )
            for amenity in rate_plan.amenities
        ]

    @staticmethod
    def _guests(requested_room: RoomOfferRequestedRoom) -> list[RoomOfferGuest]:
        guests = [
            RoomOfferGuest(guest_index=index, type=RoomOfferGuestType.ADULT)
            for index in range(requested_room.adults)
        ]
        offset = requested_room.adults
        guests.extend(
            RoomOfferGuest(
                guest_index=offset + index,
                type=RoomOfferGuestType.CHILD,
                age=child.age,
            )
            for index, child in enumerate(requested_room.children)
        )
        return guests

    @staticmethod
    def _programs_for_guest(
        programs: list[TreatmentProgram],
        guest: RoomOfferGuest,
        package_kind: TreatmentStayPackageKind,
    ) -> list[TreatmentProgram]:
        if guest.type == RoomOfferGuestType.ADULT:
            allowed = {
                TreatmentGuestApplicability.ALL,
                TreatmentGuestApplicability.ADULT,
            }
        else:
            allowed = {
                TreatmentGuestApplicability.ALL,
                TreatmentGuestApplicability.CHILD,
            }
        return [
            program
            for program in programs
            if program.guest_applicability in allowed
            and program.stay_package_kind == package_kind
        ]

    @classmethod
    def _guest_options(
        cls, payload: RoomOfferSearchRequest
    ) -> dict[tuple[int, int], RoomOfferGuestOption]:
        options: dict[tuple[int, int], RoomOfferGuestOption] = {}
        for item in payload.guest_options:
            if item.room_index >= len(payload.rooms):
                continue
            if item.guest_index >= payload.rooms[item.room_index].guests_count:
                continue
            options[(item.room_index, item.guest_index)] = item
        for room_index, room in enumerate(payload.rooms):
            for guest in cls._guests(room):
                options.setdefault(
                    (room_index, guest.guest_index),
                    cls._default_guest_option(room_index, guest.guest_index),
                )
        cls._assert_single_board(options)
        return options

    @staticmethod
    def _assert_single_board(
        options: dict[tuple[int, int], RoomOfferGuestOption],
    ) -> None:
        boards = {option.board for option in options.values()}
        if len(boards) > 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="All guests in one room-offer search must use the same board",
            )

    @staticmethod
    def _guest_option(
        context: _OfferContext, room_index: int, guest_index: int
    ) -> RoomOfferGuestOption:
        return context.guest_options.get(
            (room_index, guest_index),
            RoomOfferService._default_guest_option(room_index, guest_index),
        )

    @staticmethod
    def _default_guest_option(
        room_index: int, guest_index: int
    ) -> RoomOfferGuestOption:
        return RoomOfferGuestOption(
            room_index=room_index,
            guest_index=guest_index,
            board=BoardType.FULL_BOARD,
            treatment_included=True,
        )

    @staticmethod
    def _program_kind(option: RoomOfferGuestOption) -> TreatmentStayPackageKind:
        return (
            TreatmentStayPackageKind.TREATMENT
            if option.treatment_included
            else TreatmentStayPackageKind.SPECIAL
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
                if offer.price.total >= payload.filters.price_min
            ]
        if payload.filters.price_max is not None:
            result = [
                offer
                for offer in result
                if offer.price.total <= payload.filters.price_max
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
            usage = await self._max_used_by_room(
                room_ids=[room.id for room in rooms], dates=dates
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
        cheapest: tuple[Decimal, str] | None = None
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
            exchange_rate=context.exchange_rate,
        )
        for room in rooms:
            if not self._room_fits_request(
                alt_context, room, self._available_rooms(room, usage)
            ):
                continue
            total = self._room_total(alt_context, room, None)
            if cheapest is None or total < cheapest[0]:
                cheapest = (total, room.base_currency)
        return cheapest


def get_room_offer_service(
    db: AsyncSession = Depends(get_db),
    rates: ExchangeRateService = Depends(get_exchange_rate_service),
) -> RoomOfferService:
    return RoomOfferService(db, rates)
