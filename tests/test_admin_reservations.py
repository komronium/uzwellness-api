from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sanatorium import SanatoriumStatus
from tests.factories import make_room, make_sanatorium

_CHECK_IN = "2027-03-10"
_CHECK_OUT = "2027-03-14"


async def test_admin_reservation_dashboard_filters_and_process(
    client: AsyncClient,
    db: AsyncSession,
    admin_user,
    admin_headers,
    customer_headers,
):
    sanatorium = await make_sanatorium(
        db, status=SanatoriumStatus.APPROVED, admin_user_id=admin_user.id
    )
    room = await make_room(db, sanatorium=sanatorium, name="Superior Twin")

    create = await client.post(
        "/api/bookings",
        json={
            "room_id": str(room.id),
            "check_in": _CHECK_IN,
            "check_out": _CHECK_OUT,
            "guests": 1,
            "guest_details": [{"full_name": "KIM/SUNGSOO"}],
            "special_requests": "Late arrival",
        },
        headers=customer_headers,
    )
    assert create.status_code == 201, create.text
    booking = create.json()
    assert len(booking["reservation_number"]) == 16
    assert booking["is_processed"] is False
    assert booking["special_requests"] == "Late arrival"

    dashboard = await client.get(
        "/api/bookings/dashboard",
        params={"activity_date": _CHECK_IN},
        headers=admin_headers,
    )
    assert dashboard.status_code == 200, dashboard.text
    body = dashboard.json()
    assert body["stats"]["unprocessed_reservations"] == 1
    assert body["stats"]["checking_in_today"] == 1
    assert body["unprocessed"][0]["guest_name"] == "KIM/SUNGSOO"
    assert body["unprocessed"][0]["room_type"] == "Superior Twin"
    assert body["unprocessed"][0]["has_special_requests"] is True

    filtered = await client.get(
        "/api/bookings",
        params={
            "q": booking["reservation_number"],
            "is_processed": "false",
            "date_filter": "check_in",
            "date_from": _CHECK_IN,
            "date_to": _CHECK_IN,
        },
        headers=admin_headers,
    )
    assert filtered.status_code == 200, filtered.text
    assert filtered.json()["total"] == 1

    processed = await client.patch(
        f"/api/bookings/{booking['id']}/process", headers=admin_headers
    )
    assert processed.status_code == 200, processed.text
    assert processed.json()["is_processed"] is True
    assert processed.json()["processed_by_id"] is not None


async def test_admin_updates_reservation_settings(
    client: AsyncClient,
    db: AsyncSession,
    admin_user,
    admin_headers,
):
    sanatorium = await make_sanatorium(
        db, status=SanatoriumStatus.APPROVED, admin_user_id=admin_user.id
    )

    update = await client.patch(
        f"/api/sanatoriums/{sanatorium.id}/reservation-settings",
        json={
            "reservation_auto_confirmation_enabled": False,
            "reservation_fallback_processing_method": "email",
            "reservation_fallback_contact_name": "Reservations",
            "reservation_fallback_contact": "info@example.uz",
        },
        headers=admin_headers,
    )
    assert update.status_code == 200, update.text
    assert update.json() == {
        "reservation_auto_confirmation_enabled": False,
        "reservation_fallback_processing_method": "email",
        "reservation_fallback_contact_name": "Reservations",
        "reservation_fallback_contact": "info@example.uz",
    }

    read = await client.get(
        f"/api/sanatoriums/{sanatorium.id}/reservation-settings",
        headers=admin_headers,
    )
    assert read.status_code == 200, read.text
    assert read.json()["reservation_fallback_contact"] == "info@example.uz"
