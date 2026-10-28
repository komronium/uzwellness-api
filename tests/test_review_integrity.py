"""Who may publish a review, and what it may claim about itself.

Reviews move a property's public rating the moment they are written, so a
guest review has to come from that guest's own finished stay, and only the
platform may import reviews from other sites under their names.
"""

from datetime import timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import today_tashkent
from app.models.booking import Booking, BookingStatus, BookingType
from app.models.user import User
from tests.factories import make_room, make_sanatorium, make_user


async def _stay(
    db: AsyncSession,
    owner: User,
    sanatorium,
    *,
    status: BookingStatus = BookingStatus.COMPLETED,
    ended_days_ago: int = 1,
) -> Booking:
    room = await make_room(db, sanatorium=sanatorium)
    check_out = today_tashkent() - timedelta(days=ended_days_ago)
    booking = Booking(
        user_id=owner.id,
        room_id=room.id,
        booking_type=BookingType.ROOM,
        check_in=check_out - timedelta(days=3),
        check_out=check_out,
        guests=1,
        status=status,
        final_price=Decimal("300.00"),
        currency="USD",
    )
    db.add(booking)
    await db.commit()
    await db.refresh(booking)
    return booking


def _review(**extra) -> dict:
    return {
        "reviewer_name": "Guest",
        "rating": 5,
        "body": "Lovely stay and very attentive staff.",
        **extra,
    }


async def test_a_guest_reviews_their_own_finished_stay(
    client: AsyncClient, db: AsyncSession, customer_user, customer_headers
):
    sanatorium = await make_sanatorium(db, slug="review-own-stay")
    booking = await _stay(db, customer_user, sanatorium)

    resp = await client.post(
        f"/api/reviews/sanatoriums/{sanatorium.id}",
        json=_review(booking_id=str(booking.id)),
        headers=customer_headers,
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["source"] == "uzwellness"


async def test_a_review_without_a_stay_is_refused(
    client: AsyncClient, db: AsyncSession, customer_headers
):
    sanatorium = await make_sanatorium(db, slug="review-no-stay")

    resp = await client.post(
        f"/api/reviews/sanatoriums/{sanatorium.id}",
        json=_review(),
        headers=customer_headers,
    )

    assert resp.status_code == 400, resp.text
    assert "booking" in resp.json()["detail"].lower()


async def test_someone_elses_booking_cannot_be_reviewed(
    client: AsyncClient, db: AsyncSession, customer_headers
):
    sanatorium = await make_sanatorium(db, slug="review-other-guest")
    stranger = await make_user(db, email="review-stranger@test.com")
    booking = await _stay(db, stranger, sanatorium)

    resp = await client.post(
        f"/api/reviews/sanatoriums/{sanatorium.id}",
        json=_review(booking_id=str(booking.id)),
        headers=customer_headers,
    )

    assert resp.status_code == 404, resp.text


async def test_a_stay_elsewhere_cannot_review_this_property(
    client: AsyncClient, db: AsyncSession, customer_user, customer_headers
):
    reviewed = await make_sanatorium(db, slug="review-target")
    elsewhere = await make_sanatorium(db, slug="review-elsewhere")
    booking = await _stay(db, customer_user, elsewhere)

    resp = await client.post(
        f"/api/reviews/sanatoriums/{reviewed.id}",
        json=_review(booking_id=str(booking.id)),
        headers=customer_headers,
    )

    assert resp.status_code == 400, resp.text


async def test_a_stay_that_has_not_ended_cannot_be_reviewed_yet(
    client: AsyncClient, db: AsyncSession, customer_user, customer_headers
):
    sanatorium = await make_sanatorium(db, slug="review-future")
    booking = await _stay(
        db,
        customer_user,
        sanatorium,
        status=BookingStatus.CONFIRMED,
        ended_days_ago=-5,
    )

    resp = await client.post(
        f"/api/reviews/sanatoriums/{sanatorium.id}",
        json=_review(booking_id=str(booking.id)),
        headers=customer_headers,
    )

    assert resp.status_code == 400, resp.text


async def test_a_paid_stay_past_check_out_counts_before_the_nightly_job(
    client: AsyncClient, db: AsyncSession, customer_user, customer_headers
):
    """``completed`` is set by a nightly job; a paid stay that has ended is
    just as real while it waits for it."""

    sanatorium = await make_sanatorium(db, slug="review-confirmed-ended")
    booking = await _stay(db, customer_user, sanatorium, status=BookingStatus.CONFIRMED)

    resp = await client.post(
        f"/api/reviews/sanatoriums/{sanatorium.id}",
        json=_review(booking_id=str(booking.id)),
        headers=customer_headers,
    )

    assert resp.status_code == 201, resp.text


async def test_an_unpaid_or_cancelled_stay_cannot_be_reviewed(
    client: AsyncClient, db: AsyncSession, customer_user, customer_headers
):
    sanatorium = await make_sanatorium(db, slug="review-unpaid")
    for status in (BookingStatus.PENDING, BookingStatus.CANCELLED):
        booking = await _stay(db, customer_user, sanatorium, status=status)

        resp = await client.post(
            f"/api/reviews/sanatoriums/{sanatorium.id}",
            json=_review(booking_id=str(booking.id)),
            headers=customer_headers,
        )

        assert resp.status_code == 400, (status, resp.text)


async def test_one_stay_gets_one_review(
    client: AsyncClient, db: AsyncSession, customer_user, customer_headers
):
    sanatorium = await make_sanatorium(db, slug="review-once")
    booking = await _stay(db, customer_user, sanatorium)
    url = f"/api/reviews/sanatoriums/{sanatorium.id}"

    first = await client.post(
        url, json=_review(booking_id=str(booking.id)), headers=customer_headers
    )
    second = await client.post(
        url, json=_review(booking_id=str(booking.id)), headers=customer_headers
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 409, second.text


async def test_a_guest_cannot_pass_a_review_off_as_imported(
    client: AsyncClient, db: AsyncSession, customer_user, customer_headers
):
    sanatorium = await make_sanatorium(db, slug="review-fake-source")
    booking = await _stay(db, customer_user, sanatorium)

    resp = await client.post(
        f"/api/reviews/sanatoriums/{sanatorium.id}",
        json=_review(
            booking_id=str(booking.id),
            source="booking_com",
            external_url="https://booking.com/r/1",
        ),
        headers=customer_headers,
    )

    assert resp.status_code == 403, resp.text


async def test_a_property_admin_cannot_review_their_own_property(
    client: AsyncClient, db: AsyncSession, admin_user, admin_headers
):
    sanatorium = await make_sanatorium(
        db, slug="review-self-praise", admin_user_id=admin_user.id
    )

    resp = await client.post(
        f"/api/reviews/sanatoriums/{sanatorium.id}",
        json=_review(),
        headers=admin_headers,
    )

    assert resp.status_code == 400, resp.text


async def test_the_platform_still_imports_reviews_from_other_sites(
    client: AsyncClient, db: AsyncSession, super_admin_headers
):
    sanatorium = await make_sanatorium(db, slug="review-import")

    resp = await client.post(
        f"/api/reviews/sanatoriums/{sanatorium.id}",
        json=_review(source="trip_com", external_id="t-1"),
        headers=super_admin_headers,
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["source"] == "trip_com"
