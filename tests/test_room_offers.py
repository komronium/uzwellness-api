from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.availability import RoomAvailability
from app.models.program import (
    TreatmentGuestApplicability,
    TreatmentProgram,
    TreatmentProgramType,
    TreatmentStayPackageKind,
)
from app.models.rate_plan import BoardType, ConfirmationType, PaymentTiming, RatePlan
from app.models.sanatorium import SanatoriumStatus
from app.models.stay_option import SanatoriumStayOptionPrice, StayOptionGuestType
from tests.factories import make_room, make_sanatorium


async def _rate_plan(
    db: AsyncSession, room_id, *, board: BoardType = BoardType.FULL_BOARD
) -> RatePlan:
    name = {
        BoardType.FULL_BOARD: "Full board and treatment",
        BoardType.HALF_BOARD: "Half board and treatment",
    }.get(board, board.value.replace("_", " ").title())
    rate_plan = RatePlan(
        room_id=room_id,
        name={"en": name},
        board=board,
        payment_timing=PaymentTiming.AT_HOTEL,
        confirmation=ConfirmationType.INSTANT,
    )
    db.add(rate_plan)
    await db.commit()
    await db.refresh(rate_plan)
    return rate_plan


async def _program(db: AsyncSession, sanatorium_id, *, price: str) -> TreatmentProgram:
    program = TreatmentProgram(
        sanatorium_id=sanatorium_id,
        name={"en": "Traditional cure Basic"},
        description={"en": "1 medical examination, 10 medical procedures"},
        program_type=TreatmentProgramType.STAY_PACKAGE,
        min_nights=1,
        price=Decimal(price),
        currency="USD",
        instructor_bio={},
        what_to_bring={},
    )
    db.add(program)
    await db.commit()
    await db.refresh(program)
    return program


async def _special_package(
    db: AsyncSession, sanatorium_id, *, price: str
) -> TreatmentProgram:
    program = TreatmentProgram(
        sanatorium_id=sanatorium_id,
        name={"en": "Visiting the swimming pool"},
        description={"en": "access to the thermal pool, access to wellness"},
        program_type=TreatmentProgramType.STAY_PACKAGE,
        stay_package_kind=TreatmentStayPackageKind.SPECIAL,
        min_nights=1,
        price=Decimal(price),
        currency="USD",
        instructor_bio={},
        what_to_bring={},
    )
    db.add(program)
    await db.commit()
    await db.refresh(program)
    return program


async def _stay_option(
    db: AsyncSession,
    sanatorium_id,
    *,
    guest_type: StayOptionGuestType,
    board: BoardType,
    treatment_included: bool,
    price_delta: str,
) -> SanatoriumStayOptionPrice:
    row = SanatoriumStayOptionPrice(
        sanatorium_id=sanatorium_id,
        guest_type=guest_type,
        board=board,
        treatment_included=treatment_included,
        price_delta=Decimal(price_delta),
        currency="USD",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def test_room_offer_search_returns_guest_level_treatment_and_inclusions(
    client, db: AsyncSession, admin_user
) -> None:
    sanatorium = await make_sanatorium(
        db,
        status=SanatoriumStatus.APPROVED,
        admin_user_id=admin_user.id,
    )
    room = await make_room(
        db,
        sanatorium=sanatorium,
        name="Double Room Lux",
        capacity=3,
        inventory_count=2,
    )
    await _rate_plan(db, room.id)
    await _program(db, sanatorium.id, price="10.00")

    resp = await client.post(
        f"/api/sanatoriums/{sanatorium.id}/room-offers/search?lang=en",
        json={
            "check_in": "2026-10-02",
            "check_out": "2026-10-04",
            "rooms": [{"adults": 2, "children": [{"age": 11}]}],
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["available_count"] == 1
    assert body["adults"] == 2
    assert body["children"] == 1
    assert len(body["treatment_selection"]) == 3
    assert body["offers"][0]["room_name"] == "Double Room Lux"
    assert body["offers"][0]["price"]["total"] == "230.00"
    assert body["offers"][0]["price"]["payment_timing"] == "at_hotel"
    assert len(body["offers"][0]["inclusions"]) == 3


async def test_room_offer_search_supports_guest_board_and_no_treatment_options(
    client, db: AsyncSession, admin_user
) -> None:
    sanatorium = await make_sanatorium(
        db,
        status=SanatoriumStatus.APPROVED,
        admin_user_id=admin_user.id,
    )
    room = await make_room(
        db,
        sanatorium=sanatorium,
        name="Double Room Standard",
        capacity=3,
        inventory_count=2,
    )
    await _rate_plan(db, room.id)
    half_board_rate = await _rate_plan(db, room.id, board=BoardType.HALF_BOARD)
    treatment = await _program(db, sanatorium.id, price="10.00")
    special = await _special_package(db, sanatorium.id, price="3.00")

    resp = await client.post(
        f"/api/sanatoriums/{sanatorium.id}/room-offers/search?lang=en",
        json={
            "check_in": "2026-10-02",
            "check_out": "2026-10-04",
            "rooms": [{"adults": 2, "children": [{"age": 11}]}],
            "guest_options": [
                {
                    "room_index": 0,
                    "guest_index": 0,
                    "board": "half_board",
                    "treatment_included": False,
                },
                {
                    "room_index": 0,
                    "guest_index": 1,
                    "board": "half_board",
                    "treatment_included": True,
                },
                {
                    "room_index": 0,
                    "guest_index": 2,
                    "board": "half_board",
                    "treatment_included": False,
                },
            ],
            "treatment_selections": [
                {
                    "room_index": 0,
                    "guest_index": 1,
                    "program_id": str(treatment.id),
                }
            ],
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["available_count"] == 1
    assert body["offers"][0]["rate_plan_id"] == str(half_board_rate.id)
    groups = body["treatment_selection"]
    assert groups[0]["package_kind"] == "special"
    assert groups[0]["board"] == "half_board"
    assert groups[0]["selected_program_id"] == str(special.id)
    assert groups[0]["options"][0]["id"] == str(special.id)
    assert groups[1]["package_kind"] == "treatment"
    assert groups[1]["board"] == "half_board"
    assert groups[1]["selected_program_id"] == str(treatment.id)
    assert groups[2]["package_kind"] == "special"

    inclusions = body["offers"][0]["inclusions"]
    assert inclusions[0]["items"][0]["description"] == "2 night(s), 2 meals a day"
    assert inclusions[0]["items"][-1]["type"] == "special_package"
    assert inclusions[1]["items"][0]["description"] == "2 night(s), 2 meals a day"
    assert inclusions[1]["items"][-1]["type"] == "treatment"
    assert body["offers"][0]["price"]["total"] == "216.00"


async def test_room_offer_search_rejects_conflicting_guest_boards(
    client, db: AsyncSession, admin_user
) -> None:
    sanatorium = await make_sanatorium(
        db,
        status=SanatoriumStatus.APPROVED,
        admin_user_id=admin_user.id,
    )
    room = await make_room(
        db,
        sanatorium=sanatorium,
        name="Family Suite",
        capacity=3,
        inventory_count=2,
    )
    await _rate_plan(db, room.id)
    await _rate_plan(db, room.id, board=BoardType.HALF_BOARD)
    await _program(db, sanatorium.id, price="10.00")
    await _special_package(db, sanatorium.id, price="3.00")

    resp = await client.post(
        f"/api/sanatoriums/{sanatorium.id}/room-offers/search?lang=en",
        json={
            "check_in": "2026-10-02",
            "check_out": "2026-10-04",
            "rooms": [{"adults": 3, "children": []}],
            "guest_options": [
                {
                    "room_index": 0,
                    "guest_index": 0,
                    "board": "full_board",
                    "treatment_included": True,
                },
                {
                    "room_index": 0,
                    "guest_index": 1,
                    "board": "full_board",
                    "treatment_included": True,
                },
                {
                    "room_index": 0,
                    "guest_index": 2,
                    "board": "half_board",
                    "treatment_included": False,
                },
            ],
        },
    )

    assert resp.status_code == 400
    assert (
        resp.json()["detail"]
        == "All guests in one room-offer search must use the same board"
    )


async def test_room_offer_search_prices_guest_stay_options(
    client, db: AsyncSession, admin_user
) -> None:
    sanatorium = await make_sanatorium(
        db,
        status=SanatoriumStatus.APPROVED,
        admin_user_id=admin_user.id,
    )
    room = await make_room(
        db,
        sanatorium=sanatorium,
        name="Double Room Standard",
        capacity=3,
        inventory_count=2,
    )
    await _rate_plan(db, room.id, board=BoardType.HALF_BOARD)
    treatment = await _program(db, sanatorium.id, price="10.00")
    await _special_package(db, sanatorium.id, price="3.00")
    await _stay_option(
        db,
        sanatorium.id,
        guest_type=StayOptionGuestType.ADULT,
        board=BoardType.HALF_BOARD,
        treatment_included=False,
        price_delta="5.00",
    )
    await _stay_option(
        db,
        sanatorium.id,
        guest_type=StayOptionGuestType.ADULT,
        board=BoardType.HALF_BOARD,
        treatment_included=True,
        price_delta="8.00",
    )
    await _stay_option(
        db,
        sanatorium.id,
        guest_type=StayOptionGuestType.CHILD,
        board=BoardType.HALF_BOARD,
        treatment_included=False,
        price_delta="2.00",
    )

    resp = await client.post(
        f"/api/sanatoriums/{sanatorium.id}/room-offers/search?lang=en",
        json={
            "check_in": "2026-10-02",
            "check_out": "2026-10-04",
            "rooms": [{"adults": 2, "children": [{"age": 11}]}],
            "guest_options": [
                {
                    "room_index": 0,
                    "guest_index": 0,
                    "board": "half_board",
                    "treatment_included": False,
                },
                {
                    "room_index": 0,
                    "guest_index": 1,
                    "board": "half_board",
                    "treatment_included": True,
                },
                {
                    "room_index": 0,
                    "guest_index": 2,
                    "board": "half_board",
                    "treatment_included": False,
                },
            ],
            "treatment_selections": [
                {
                    "room_index": 0,
                    "guest_index": 1,
                    "program_id": str(treatment.id),
                }
            ],
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["offers"][0]["price"]["total"] == "246.00"


async def test_room_offer_search_rejects_unavailable_stay_option(
    client, db: AsyncSession, admin_user
) -> None:
    sanatorium = await make_sanatorium(
        db,
        status=SanatoriumStatus.APPROVED,
        admin_user_id=admin_user.id,
    )
    room = await make_room(db, sanatorium=sanatorium, capacity=2)
    await _rate_plan(db, room.id)
    await _stay_option(
        db,
        sanatorium.id,
        guest_type=StayOptionGuestType.ADULT,
        board=BoardType.FULL_BOARD,
        treatment_included=True,
        price_delta="0.00",
    )

    resp = await client.post(
        f"/api/sanatoriums/{sanatorium.id}/room-offers/search?lang=en",
        json={
            "check_in": "2026-10-02",
            "check_out": "2026-10-04",
            "rooms": [{"adults": 1, "children": []}],
            "guest_options": [
                {
                    "room_index": 0,
                    "guest_index": 0,
                    "board": "half_board",
                    "treatment_included": True,
                }
            ],
        },
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Selected stay option is not available"


async def test_room_offer_search_respects_explicit_room_distribution(
    client, db: AsyncSession, admin_user
) -> None:
    sanatorium = await make_sanatorium(
        db,
        status=SanatoriumStatus.APPROVED,
        admin_user_id=admin_user.id,
    )
    room = await make_room(
        db,
        sanatorium=sanatorium,
        capacity=3,
        inventory_count=2,
    )
    await _rate_plan(db, room.id)

    resp = await client.post(
        f"/api/sanatoriums/{sanatorium.id}/room-offers/search?lang=en",
        json={
            "check_in": "2026-10-02",
            "check_out": "2026-10-04",
            "rooms": [
                {"adults": 2, "children": [{"age": 11}]},
                {"adults": 2, "children": []},
            ],
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["available_count"] == 1
    assert body["rooms_count"] == 2
    assert body["guests"] == 5
    assert body["offers"][0]["price"]["rooms_count"] == 2
    assert body["offers"][0]["price"]["total"] == "400.00"


async def test_room_offer_search_returns_alternative_dates_when_requested_dates_full(
    client, db: AsyncSession, admin_user
) -> None:
    sanatorium = await make_sanatorium(
        db,
        status=SanatoriumStatus.APPROVED,
        admin_user_id=admin_user.id,
    )
    room = await make_room(
        db,
        sanatorium=sanatorium,
        capacity=2,
        inventory_count=1,
    )
    db.add_all(
        [
            RoomAvailability(
                room_id=room.id,
                date=date(2026, 10, 2),
                units_blocked=1,
                units_booked=0,
            ),
            RoomAvailability(
                room_id=room.id,
                date=date(2026, 10, 3),
                units_blocked=1,
                units_booked=0,
            ),
        ]
    )
    await db.commit()

    resp = await client.post(
        f"/api/sanatoriums/{sanatorium.id}/room-offers/search?lang=en",
        json={
            "check_in": "2026-10-02",
            "check_out": "2026-10-04",
            "rooms": [{"adults": 2, "children": []}],
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["available_count"] == 0
    assert body["offers"] == []
    assert body["alternatives"]
    assert body["alternatives"][0]["nights"] == 2


async def test_room_offer_booking_recalculates_and_reserves_inventory(
    client, db: AsyncSession, customer_headers, admin_user
) -> None:
    sanatorium = await make_sanatorium(
        db,
        status=SanatoriumStatus.APPROVED,
        admin_user_id=admin_user.id,
    )
    room = await make_room(
        db,
        sanatorium=sanatorium,
        name="Double Room Lux",
        capacity=3,
        inventory_count=2,
    )
    rate_plan = await _rate_plan(db, room.id)
    program = await _program(db, sanatorium.id, price="10.00")

    resp = await client.post(
        "/api/bookings/room-offer?lang=en",
        headers=customer_headers,
        json={
            "sanatorium_id": str(sanatorium.id),
            "room_id": str(room.id),
            "rate_plan_id": str(rate_plan.id),
            "check_in": "2026-10-02",
            "check_out": "2026-10-04",
            "rooms": [{"adults": 2, "children": [{"age": 11}]}],
            "guest_options": [
                {
                    "room_index": 0,
                    "guest_index": 0,
                    "board": "half_board",
                    "treatment_included": True,
                }
            ],
            "treatment_selections": [
                {
                    "room_index": 0,
                    "guest_index": 0,
                    "program_id": str(program.id),
                }
            ],
        },
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["room_id"] == str(room.id)
    assert body["rate_plan_id"] == str(rate_plan.id)
    assert body["guests"] == 3
    assert body["adults"] == 2
    assert body["children"] == 1
    assert body["rooms_count"] == 1
    assert body["final_price"] == "230.00"
    assert body["guest_options"] == [
        {
            "room_index": 0,
            "guest_index": 0,
            "board": "half_board",
            "treatment_included": True,
        }
    ]
    assert body["room_distribution"] == [{"adults": 2, "children": [{"age": 11}]}]
    assert body["offer_snapshot"]["room_name"] == "Double Room Lux"

    availability_rows = (
        await db.scalars(
            select(RoomAvailability).where(RoomAvailability.room_id == room.id)
        )
    ).all()
    assert len(availability_rows) == 2
    assert all(row.units_booked == 1 for row in availability_rows)


async def test_room_offer_booking_rejects_stale_offer(
    client, db: AsyncSession, customer_headers, admin_user
) -> None:
    sanatorium = await make_sanatorium(
        db,
        status=SanatoriumStatus.APPROVED,
        admin_user_id=admin_user.id,
    )
    room = await make_room(
        db,
        sanatorium=sanatorium,
        capacity=2,
        inventory_count=1,
    )
    db.add_all(
        [
            RoomAvailability(
                room_id=room.id,
                date=date(2026, 10, 2),
                units_blocked=1,
                units_booked=0,
            ),
            RoomAvailability(
                room_id=room.id,
                date=date(2026, 10, 3),
                units_blocked=1,
                units_booked=0,
            ),
        ]
    )
    await db.commit()

    resp = await client.post(
        "/api/bookings/room-offer?lang=en",
        headers=customer_headers,
        json={
            "sanatorium_id": str(sanatorium.id),
            "room_id": str(room.id),
            "check_in": "2026-10-02",
            "check_out": "2026-10-04",
            "rooms": [{"adults": 2, "children": []}],
        },
    )

    assert resp.status_code == 409
    assert "no longer available" in resp.json()["detail"]


async def test_room_offer_booking_rejects_guest_incompatible_treatment(
    client, db: AsyncSession, customer_headers, admin_user
) -> None:
    sanatorium = await make_sanatorium(
        db,
        status=SanatoriumStatus.APPROVED,
        admin_user_id=admin_user.id,
    )
    room = await make_room(
        db,
        sanatorium=sanatorium,
        capacity=3,
        inventory_count=1,
    )
    adult_only = TreatmentProgram(
        sanatorium_id=sanatorium.id,
        name={"en": "Adult intensive cure"},
        description={"en": "Adult-only treatment package"},
        program_type=TreatmentProgramType.STAY_PACKAGE,
        guest_applicability=TreatmentGuestApplicability.ADULT,
        min_nights=1,
        price=Decimal("0.00"),
        currency="USD",
        instructor_bio={},
        what_to_bring={},
    )
    db.add(adult_only)
    await db.commit()
    await db.refresh(adult_only)

    resp = await client.post(
        "/api/bookings/room-offer?lang=en",
        headers=customer_headers,
        json={
            "sanatorium_id": str(sanatorium.id),
            "room_id": str(room.id),
            "check_in": "2026-10-02",
            "check_out": "2026-10-04",
            "rooms": [{"adults": 1, "children": [{"age": 11}]}],
            "treatment_selections": [
                {
                    "room_index": 0,
                    "guest_index": 1,
                    "program_id": str(adult_only.id),
                }
            ],
        },
    )

    assert resp.status_code == 400
    assert (
        resp.json()["detail"] == "Treatment selection is not available for this guest"
    )
