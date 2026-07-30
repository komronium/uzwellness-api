"""transfer_admin role, tariff versioning, checkout add-on and finance."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.sanatorium import SanatoriumStatus
from app.models.transfer_request import TransferRequest
from app.models.user import User, UserRole
from tests.factories import make_exchange_rate, make_room, make_sanatorium, make_user

_CHECK_IN = "2027-05-10"
_CHECK_OUT = "2027-05-13"
_FLIGHT_TIME = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
_RETURN_TIME = (datetime.now(timezone.utc) + timedelta(days=34)).isoformat()


# ── fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
async def transfer_admin_user(db: AsyncSession) -> User:
    user = await make_user(
        db,
        email="transfer@test.com",
        password="transferpass123",
        role=UserRole.TRANSFER_ADMIN,
    )
    user.transfer_commission_percent = Decimal("15.00")
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
async def transfer_admin_headers(
    client: AsyncClient, transfer_admin_user: User
) -> dict[str, str]:
    resp = await client.post(
        "/api/auth/login",
        json={"email": transfer_admin_user.email, "password": "transferpass123"},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _make_location(client: AsyncClient, headers: dict, name: str, kind: str):
    resp = await client.post(
        "/api/transfer-locations",
        json={
            "name": {"uz": name, "ru": name, "en": name},
            "kind": kind,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.fixture
async def route(client: AsyncClient, transfer_admin_headers) -> tuple[str, str]:
    airport = await _make_location(
        client, transfer_admin_headers, "Tashkent Airport", "airport"
    )
    resort = await _make_location(
        client, transfer_admin_headers, "Charvak Resort", "sanatorium"
    )
    return airport, resort


async def _publish_tariff(
    client: AsyncClient,
    headers: dict,
    route_from: str,
    route_to: str,
    price: str,
    *,
    vehicle_type: str = "sedan",
    currency: str = "USD",
):
    resp = await client.post(
        "/api/transfer-tariffs",
        json={
            "route_from_id": route_from,
            "route_to_id": route_to,
            "vehicle_type": vehicle_type,
            "price": price,
            "currency": currency,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── role ───────────────────────────────────────────────────────────────────


class TestTransferAdminRole:
    async def test_second_transfer_admin_is_rejected(
        self, client: AsyncClient, super_admin_headers, transfer_admin_user
    ):
        resp = await client.post(
            "/api/users",
            json={
                "email": "second-transfer@test.com",
                "password": "anotherpass123",
                "role": "transfer_admin",
                "transfer_commission_percent": "10.00",
            },
            headers=super_admin_headers,
        )
        assert resp.status_code == 409, resp.text
        detail = resp.json()["detail"]
        assert detail["code"] == "transfer_admin_exists"
        assert detail["existing_user_id"] == str(transfer_admin_user.id)

    async def test_create_without_commission_is_422(
        self, client: AsyncClient, super_admin_headers
    ):
        resp = await client.post(
            "/api/users",
            json={
                "email": "no-commission@test.com",
                "password": "anotherpass123",
                "role": "transfer_admin",
            },
            headers=super_admin_headers,
        )
        assert resp.status_code == 422, resp.text

    async def test_create_transfer_admin_persists_commission(
        self, client: AsyncClient, super_admin_headers
    ):
        resp = await client.post(
            "/api/users",
            json={
                "email": "the-operator@test.com",
                "password": "anotherpass123",
                "role": "transfer_admin",
                "transfer_commission_percent": "12.50",
            },
            headers=super_admin_headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["transfer_commission_percent"] == "12.50"

    async def test_promoting_second_user_is_rejected(
        self,
        client: AsyncClient,
        super_admin_headers,
        customer_user,
        transfer_admin_user,
    ):
        resp = await client.patch(
            f"/api/users/{customer_user.id}",
            json={"role": "transfer_admin", "transfer_commission_percent": "10.00"},
            headers=super_admin_headers,
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"]["code"] == "transfer_admin_exists"

    async def test_demoting_clears_commission(
        self, client: AsyncClient, super_admin_headers, transfer_admin_user
    ):
        resp = await client.patch(
            f"/api/users/{transfer_admin_user.id}",
            json={"role": "customer"},
            headers=super_admin_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["transfer_commission_percent"] is None


# ── tariffs ────────────────────────────────────────────────────────────────


class TestTariffVersioning:
    async def test_post_supersedes_previous_version(
        self, client: AsyncClient, transfer_admin_headers, route
    ):
        airport, resort = route
        first = await _publish_tariff(
            client, transfer_admin_headers, airport, resort, "40.00"
        )
        assert first["is_current"] is True
        assert first["effective_to"] is None

        second = await _publish_tariff(
            client, transfer_admin_headers, airport, resort, "55.00"
        )
        assert second["is_current"] is True

        history = await client.get(
            "/api/transfer-tariffs",
            params={"route_from_id": airport, "route_to_id": resort},
            headers=transfer_admin_headers,
        )
        assert history.status_code == 200, history.text
        items = history.json()["items"]
        assert len(items) == 2
        assert items[0]["id"] == second["id"]
        closed = next(i for i in items if i["id"] == first["id"])
        assert closed["effective_to"] is not None
        assert closed["is_current"] is False

        current = await client.get(
            "/api/transfer-tariffs/current",
            params={
                "route_from_id": airport,
                "route_to_id": resort,
                "vehicle_type": "sedan",
            },
        )
        assert current.status_code == 200, current.text
        assert current.json()["id"] == second["id"]
        assert current.json()["price"] == "55.00"

    async def test_current_is_404_without_a_tariff(self, client: AsyncClient, route):
        airport, resort = route
        resp = await client.get(
            "/api/transfer-tariffs/current",
            params={
                "route_from_id": airport,
                "route_to_id": resort,
                "vehicle_type": "bus",
            },
        )
        assert resp.status_code == 404

    async def test_customer_cannot_publish_a_tariff(
        self, client: AsyncClient, customer_headers, route
    ):
        airport, resort = route
        resp = await client.post(
            "/api/transfer-tariffs",
            json={
                "route_from_id": airport,
                "route_to_id": resort,
                "vehicle_type": "sedan",
                "price": "1.00",
                "currency": "USD",
            },
            headers=customer_headers,
        )
        assert resp.status_code == 403

    async def test_same_endpoint_twice_is_rejected(
        self, client: AsyncClient, transfer_admin_headers, route
    ):
        airport, _ = route
        resp = await client.post(
            "/api/transfer-tariffs",
            json={
                "route_from_id": airport,
                "route_to_id": airport,
                "vehicle_type": "sedan",
                "price": "10.00",
                "currency": "USD",
            },
            headers=transfer_admin_headers,
        )
        assert resp.status_code == 422


class TestLocationsAndVehicles:
    async def test_location_in_use_cannot_be_deleted(
        self, client: AsyncClient, transfer_admin_headers, route
    ):
        airport, resort = route
        await _publish_tariff(client, transfer_admin_headers, airport, resort, "40.00")
        resp = await client.delete(
            f"/api/transfer-locations/{airport}", headers=transfer_admin_headers
        )
        assert resp.status_code == 409

    async def test_vehicle_crud_and_duplicate_plate(
        self, client: AsyncClient, transfer_admin_headers
    ):
        payload = {
            "vehicle_type": "minivan",
            "capacity": 7,
            "plate": "01 A 777 AA",
            "label": "Staria",
        }
        created = await client.post(
            "/api/transfer-vehicles", json=payload, headers=transfer_admin_headers
        )
        assert created.status_code == 201, created.text

        duplicate = await client.post(
            "/api/transfer-vehicles", json=payload, headers=transfer_admin_headers
        )
        assert duplicate.status_code == 409

        listed = await client.get(
            "/api/transfer-vehicles", headers=transfer_admin_headers
        )
        assert listed.json()["total"] == 1

    async def test_customer_cannot_list_vehicles(
        self, client: AsyncClient, customer_headers
    ):
        resp = await client.get("/api/transfer-vehicles", headers=customer_headers)
        assert resp.status_code == 403


# ── checkout add-on ────────────────────────────────────────────────────────


async def _book_with_transfer(
    client: AsyncClient,
    db: AsyncSession,
    admin_user,
    customer_headers,
    route,
    *,
    transfer: dict | None,
    name: str = "Test Sanatorium",
):
    san = await make_sanatorium(
        db,
        name=name,
        status=SanatoriumStatus.APPROVED,
        admin_user_id=admin_user.id,
    )
    room = await make_room(db, sanatorium=san, capacity=2, inventory_count=3)
    body = {
        "room_id": str(room.id),
        "check_in": _CHECK_IN,
        "check_out": _CHECK_OUT,
        "guests": 2,
    }
    if transfer is not None:
        body["transfer"] = transfer
    return await client.post("/api/bookings", json=body, headers=customer_headers)


class TestBookingAddOn:
    async def test_transfer_is_priced_and_added_to_total(
        self,
        client: AsyncClient,
        db: AsyncSession,
        admin_user,
        customer_headers,
        transfer_admin_headers,
        route,
    ):
        airport, resort = route
        await _publish_tariff(client, transfer_admin_headers, airport, resort, "40.00")
        baseline = await _book_with_transfer(
            client,
            db,
            admin_user,
            customer_headers,
            route,
            transfer=None,
            name="Baseline Sanatorium",
        )
        assert baseline.status_code == 201, baseline.text
        plain_total = Decimal(baseline.json()["final_price"])

        resp = await _book_with_transfer(
            client,
            db,
            admin_user,
            customer_headers,
            route,
            transfer={
                "route_from_id": airport,
                "route_to_id": resort,
                "vehicle_type": "sedan",
                "direction": "arrival",
                "flight_number": "HY101",
                "flight_time": _FLIGHT_TIME,
                "passengers_count": 2,
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()

        assert body["transfer_price"] == "40.00"
        assert body["transfer_currency"] == "USD"
        assert Decimal(body["final_price"]) == plain_total + Decimal("40.00")
        assert body["transfer"]["payment_state"] == "included"
        assert body["transfer"]["status"] == "requested"
        assert body["transfer"]["pickup_location"] == "Tashkent Airport"
        assert body["transfer"]["dropoff_location"] == "Charvak Resort"
        # Commission is frozen from the operator's percent (15% of 40).
        assert body["transfer"]["applied_price"] == "40.00"

    async def test_round_trip_sums_both_legs(
        self,
        client: AsyncClient,
        db: AsyncSession,
        admin_user,
        customer_headers,
        transfer_admin_headers,
        route,
    ):
        airport, resort = route
        await _publish_tariff(client, transfer_admin_headers, airport, resort, "40.00")
        await _publish_tariff(client, transfer_admin_headers, resort, airport, "35.00")
        resp = await _book_with_transfer(
            client,
            db,
            admin_user,
            customer_headers,
            route,
            transfer={
                "route_from_id": airport,
                "route_to_id": resort,
                "vehicle_type": "sedan",
                "direction": "round_trip",
                "flight_time": _FLIGHT_TIME,
                "return_flight_time": _RETURN_TIME,
            },
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["transfer_price"] == "75.00"

    async def test_round_trip_without_return_leg_tariff_is_422(
        self,
        client: AsyncClient,
        db: AsyncSession,
        admin_user,
        customer_headers,
        transfer_admin_headers,
        route,
    ):
        airport, resort = route
        await _publish_tariff(client, transfer_admin_headers, airport, resort, "40.00")
        resp = await _book_with_transfer(
            client,
            db,
            admin_user,
            customer_headers,
            route,
            transfer={
                "route_from_id": airport,
                "route_to_id": resort,
                "vehicle_type": "sedan",
                "direction": "round_trip",
                "flight_time": _FLIGHT_TIME,
                "return_flight_time": _RETURN_TIME,
            },
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["detail"]["code"] == "no_tariff_for_route"

    async def test_route_without_tariff_is_422(
        self,
        client: AsyncClient,
        db: AsyncSession,
        admin_user,
        customer_headers,
        route,
    ):
        airport, resort = route
        resp = await _book_with_transfer(
            client,
            db,
            admin_user,
            customer_headers,
            route,
            transfer={
                "route_from_id": airport,
                "route_to_id": resort,
                "vehicle_type": "sedan",
                "direction": "arrival",
                "flight_time": _FLIGHT_TIME,
            },
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["detail"]["code"] == "no_tariff_for_route"

    async def test_failed_transfer_pricing_does_not_create_a_booking(
        self,
        client: AsyncClient,
        db: AsyncSession,
        admin_user,
        customer_headers,
        route,
    ):
        airport, resort = route
        await _book_with_transfer(
            client,
            db,
            admin_user,
            customer_headers,
            route,
            transfer={
                "route_from_id": airport,
                "route_to_id": resort,
                "vehicle_type": "sedan",
                "direction": "arrival",
                "flight_time": _FLIGHT_TIME,
            },
        )
        assert (await db.scalars(select(Booking))).all() == []

    async def test_tariff_currency_is_converted_to_the_booking_currency(
        self,
        client: AsyncClient,
        db: AsyncSession,
        admin_user,
        customer_headers,
        transfer_admin_headers,
        route,
    ):
        await make_exchange_rate(db, pair="USD_UZS", rate="12500")
        airport, resort = route
        # Room prices are USD; the tariff is UZS and must be converted.
        await _publish_tariff(
            client,
            transfer_admin_headers,
            airport,
            resort,
            "625000.00",
            currency="UZS",
        )
        resp = await _book_with_transfer(
            client,
            db,
            admin_user,
            customer_headers,
            route,
            transfer={
                "route_from_id": airport,
                "route_to_id": resort,
                "vehicle_type": "sedan",
                "direction": "departure",
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["currency"] == "USD"
        assert body["transfer_currency"] == "USD"
        assert body["transfer_price"] == "50.00"

    async def test_invoice_lists_the_transfer(
        self,
        client: AsyncClient,
        db: AsyncSession,
        admin_user,
        customer_headers,
        transfer_admin_headers,
        route,
    ):
        airport, resort = route
        await _publish_tariff(client, transfer_admin_headers, airport, resort, "40.00")
        booking = await _book_with_transfer(
            client,
            db,
            admin_user,
            customer_headers,
            route,
            transfer={
                "route_from_id": airport,
                "route_to_id": resort,
                "vehicle_type": "sedan",
                "direction": "departure",
            },
        )
        booking_id = booking.json()["id"]
        resp = await client.get(
            f"/api/bookings/{booking_id}/invoice", headers=customer_headers
        )
        assert resp.status_code == 200, resp.text
        invoice = resp.json()
        transfer_line = next(
            item for item in invoice["line_items"] if "Transfer" in item["description"]
        )
        assert transfer_line["amount"] == "40.00"
        assert Decimal(invoice["total"]) == sum(
            Decimal(item["amount"]) for item in invoice["line_items"]
        )

    async def test_cancelling_the_booking_cancels_the_transfer(
        self,
        client: AsyncClient,
        db: AsyncSession,
        admin_user,
        customer_headers,
        transfer_admin_headers,
        route,
    ):
        airport, resort = route
        await _publish_tariff(client, transfer_admin_headers, airport, resort, "40.00")
        booking = await _book_with_transfer(
            client,
            db,
            admin_user,
            customer_headers,
            route,
            transfer={
                "route_from_id": airport,
                "route_to_id": resort,
                "vehicle_type": "sedan",
                "direction": "departure",
            },
        )
        booking_id = booking.json()["id"]
        cancel = await client.post(
            f"/api/bookings/{booking_id}/cancel", headers=customer_headers
        )
        assert cancel.status_code == 200, cancel.text
        assert cancel.json()["transfer"]["status"] == "cancelled"


# ── post-booking add-on ────────────────────────────────────────────────────


class TestStandaloneTransfer:
    async def test_customer_order_is_priced_and_unpaid(
        self, client: AsyncClient, customer_headers, transfer_admin_headers, route
    ):
        airport, resort = route
        await _publish_tariff(client, transfer_admin_headers, airport, resort, "40.00")
        resp = await client.post(
            "/api/transfers",
            json={
                "route_from_id": airport,
                "route_to_id": resort,
                "vehicle_type": "sedan",
                "direction": "departure",
            },
            headers=customer_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["payment_state"] == "unpaid"
        assert body["applied_price"] == "40.00"
        assert body["applied_currency"] == "USD"
        assert body["pickup_location"] == "Tashkent Airport"

    async def test_free_text_order_still_works_unpriced(
        self, client: AsyncClient, customer_headers
    ):
        resp = await client.post(
            "/api/transfers",
            json={
                "direction": "departure",
                "pickup_location": "Some hotel",
                "dropoff_location": "Some airport",
            },
            headers=customer_headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["applied_price"] is None

    async def test_operator_sees_every_transfer(
        self, client: AsyncClient, customer_headers, transfer_admin_headers
    ):
        await client.post(
            "/api/transfers",
            json={
                "direction": "departure",
                "pickup_location": "A",
                "dropoff_location": "B",
            },
            headers=customer_headers,
        )
        resp = await client.get("/api/transfers", headers=transfer_admin_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["total"] == 1

    async def test_operator_assigns_a_vehicle(
        self, client: AsyncClient, customer_headers, transfer_admin_headers
    ):
        created = await client.post(
            "/api/transfers",
            json={
                "direction": "departure",
                "pickup_location": "A",
                "dropoff_location": "B",
            },
            headers=customer_headers,
        )
        transfer_id = created.json()["id"]
        vehicle = await client.post(
            "/api/transfer-vehicles",
            json={"vehicle_type": "sedan", "capacity": 3, "plate": "01 B 123 CC"},
            headers=transfer_admin_headers,
        )
        resp = await client.patch(
            f"/api/transfers/{transfer_id}",
            json={
                "vehicle_id": vehicle.json()["id"],
                "status": "confirmed",
                "driver_name": "Aziz",
            },
            headers=transfer_admin_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["vehicle_id"] == vehicle.json()["id"]
        assert resp.json()["status"] == "confirmed"

    async def test_customer_patch_is_limited_to_own_details(
        self, client: AsyncClient, customer_headers
    ):
        created = await client.post(
            "/api/transfers",
            json={
                "direction": "departure",
                "pickup_location": "A",
                "dropoff_location": "B",
            },
            headers=customer_headers,
        )
        transfer_id = created.json()["id"]

        allowed = await client.patch(
            f"/api/transfers/{transfer_id}",
            json={"flight_number": "HY202", "contact_phone": "+998901112233"},
            headers=customer_headers,
        )
        assert allowed.status_code == 200, allowed.text
        assert allowed.json()["flight_number"] == "HY202"

        denied = await client.patch(
            f"/api/transfers/{transfer_id}",
            json={"status": "confirmed"},
            headers=customer_headers,
        )
        assert denied.status_code == 403


# ── finance ────────────────────────────────────────────────────────────────


class TestTransferFinance:
    async def test_summary_reconciles_net_with_commission(
        self,
        client: AsyncClient,
        db: AsyncSession,
        admin_user,
        customer_headers,
        transfer_admin_headers,
        route,
    ):
        airport, resort = route
        await _publish_tariff(client, transfer_admin_headers, airport, resort, "40.00")
        await _book_with_transfer(
            client,
            db,
            admin_user,
            customer_headers,
            route,
            transfer={
                "route_from_id": airport,
                "route_to_id": resort,
                "vehicle_type": "sedan",
                "direction": "departure",
            },
        )
        # A second, post-booking order that stays unpaid.
        await client.post(
            "/api/transfers",
            json={
                "route_from_id": airport,
                "route_to_id": resort,
                "vehicle_type": "sedan",
                "direction": "departure",
            },
            headers=customer_headers,
        )

        resp = await client.get(
            "/api/transfer-finance/summary", headers=transfer_admin_headers
        )
        assert resp.status_code == 200, resp.text
        row = next(i for i in resp.json()["items"] if i["currency"] == "USD")
        assert row["order_count"] == 2
        assert row["gross_amount"] == "80.00"
        assert row["platform_commission_percent"] == "15.00"
        assert row["platform_commission_amount"] == "12.00"
        assert Decimal(row["net_payout_amount"]) == Decimal("80.00") - Decimal("12.00")
        assert row["unpaid_amount"] == "40.00"

    async def test_cancelled_transfers_are_excluded(
        self, client: AsyncClient, customer_headers, transfer_admin_headers, route
    ):
        airport, resort = route
        await _publish_tariff(client, transfer_admin_headers, airport, resort, "40.00")
        created = await client.post(
            "/api/transfers",
            json={
                "route_from_id": airport,
                "route_to_id": resort,
                "vehicle_type": "sedan",
                "direction": "departure",
            },
            headers=customer_headers,
        )
        await client.post(
            f"/api/transfers/{created.json()['id']}/cancel", headers=customer_headers
        )
        resp = await client.get(
            "/api/transfer-finance/summary", headers=transfer_admin_headers
        )
        assert resp.json()["items"] == []

    async def test_orders_list_carries_the_booking_code(
        self,
        client: AsyncClient,
        db: AsyncSession,
        admin_user,
        customer_headers,
        transfer_admin_headers,
        route,
    ):
        airport, resort = route
        await _publish_tariff(client, transfer_admin_headers, airport, resort, "40.00")
        booking = await _book_with_transfer(
            client,
            db,
            admin_user,
            customer_headers,
            route,
            transfer={
                "route_from_id": airport,
                "route_to_id": resort,
                "vehicle_type": "sedan",
                "direction": "departure",
            },
        )
        resp = await client.get(
            "/api/transfer-finance/orders", headers=transfer_admin_headers
        )
        assert resp.status_code == 200, resp.text
        item = resp.json()["items"][0]
        assert item["booking_code"] == booking.json()["code"]
        assert item["payment_state"] == "included"
        assert item["net_payout_amount"] == "34.00"

    async def test_customer_cannot_read_transfer_finance(
        self, client: AsyncClient, customer_headers
    ):
        resp = await client.get(
            "/api/transfer-finance/summary", headers=customer_headers
        )
        assert resp.status_code == 403

    async def test_commission_snapshot_survives_a_percent_change(
        self,
        client: AsyncClient,
        db: AsyncSession,
        customer_headers,
        transfer_admin_headers,
        transfer_admin_user,
        route,
    ):
        airport, resort = route
        await _publish_tariff(client, transfer_admin_headers, airport, resort, "40.00")
        created = await client.post(
            "/api/transfers",
            json={
                "route_from_id": airport,
                "route_to_id": resort,
                "vehicle_type": "sedan",
                "direction": "departure",
            },
            headers=customer_headers,
        )
        transfer_admin_user.transfer_commission_percent = Decimal("30.00")
        await db.commit()

        transfer = await db.scalar(
            select(TransferRequest).where(
                TransferRequest.id == uuid_of(created.json()["id"])
            )
        )
        assert transfer.commission_percent_snapshot == Decimal("15.00")
        assert transfer.commission_amount_snapshot == Decimal("6.00")


def uuid_of(value: str):
    import uuid

    return uuid.UUID(value)
