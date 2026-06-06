from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sanatorium import SanatoriumStatus
from tests.factories import make_sanatorium


async def test_admin_replaces_stay_option_prices(
    client, db: AsyncSession, admin_user, admin_headers
) -> None:
    sanatorium = await make_sanatorium(
        db,
        status=SanatoriumStatus.APPROVED,
        admin_user_id=admin_user.id,
    )

    resp = await client.put(
        f"/api/sanatoriums/{sanatorium.id}/stay-option-prices",
        headers=admin_headers,
        json={
            "items": [
                {
                    "guest_type": "adult",
                    "board": "full_board",
                    "treatment_included": True,
                    "price_delta": "15.00",
                    "currency": "usd",
                    "is_available": True,
                },
                {
                    "guest_type": "child",
                    "board": "half_board",
                    "treatment_included": False,
                    "price_delta": "5.00",
                    "currency": "UZS",
                    "is_available": False,
                },
            ]
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["items"][0]["currency"] == "USD"

    public_resp = await client.get(
        f"/api/sanatoriums/{sanatorium.id}/stay-option-prices"
    )
    assert public_resp.status_code == 200
    assert len(public_resp.json()["items"]) == 2

    replace_resp = await client.put(
        f"/api/sanatoriums/{sanatorium.id}/stay-option-prices",
        headers=admin_headers,
        json={
            "items": [
                {
                    "guest_type": "adult",
                    "board": "half_board",
                    "treatment_included": True,
                    "price_delta": "10.00",
                    "currency": "USD",
                    "is_available": True,
                }
            ]
        },
    )

    assert replace_resp.status_code == 200, replace_resp.text
    items = replace_resp.json()["items"]
    assert len(items) == 1
    assert items[0]["board"] == "half_board"


async def test_stay_option_prices_reject_duplicate_keys(
    client, db: AsyncSession, admin_user, admin_headers
) -> None:
    sanatorium = await make_sanatorium(
        db,
        status=SanatoriumStatus.APPROVED,
        admin_user_id=admin_user.id,
    )

    resp = await client.put(
        f"/api/sanatoriums/{sanatorium.id}/stay-option-prices",
        headers=admin_headers,
        json={
            "items": [
                {
                    "guest_type": "adult",
                    "board": "full_board",
                    "treatment_included": True,
                    "price_delta": "15.00",
                    "currency": "USD",
                    "is_available": True,
                },
                {
                    "guest_type": "adult",
                    "board": "full_board",
                    "treatment_included": True,
                    "price_delta": "20.00",
                    "currency": "USD",
                    "is_available": True,
                },
            ]
        },
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Duplicate stay option price"
