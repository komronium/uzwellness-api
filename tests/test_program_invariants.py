"""Program (treatment_program) invariants — price/currency move together."""

from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.program import TreatmentProgram
from tests.factories import make_sanatorium, make_user
from app.models.user import UserRole


async def _bookable_program(db: AsyncSession, *, sanatorium_id) -> TreatmentProgram:
    program = TreatmentProgram(
        sanatorium_id=sanatorium_id,
        name={"en": "Yoga session"},
        description={},
        price=Decimal("40.00"),
        currency="USD",
        instructor_bio={},
        what_to_bring={},
    )
    db.add(program)
    await db.commit()
    await db.refresh(program)
    return program


async def _super_headers(client: AsyncClient, db: AsyncSession) -> dict:
    user = await make_user(
        db,
        email="prog-super@test.com",
        password="superpass123",
        role=UserRole.SUPER_ADMIN,
    )
    login = await client.post(
        "/api/auth/login",
        json={"email": user.email, "password": "superpass123"},
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def test_patch_price_without_currency_rejected(
    client: AsyncClient, db: AsyncSession
) -> None:
    s = await make_sanatorium(db, slug="prog-inv-1")
    program = await _bookable_program(db, sanatorium_id=s.id)
    headers = await _super_headers(client, db)
    # Try to clear currency while keeping price set.
    resp = await client.patch(
        f"/api/programs/{program.id}",
        json={"currency": None},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "price and currency" in resp.json()["detail"]


async def test_patch_currency_alone_rejected_when_price_null(
    client: AsyncClient, db: AsyncSession
) -> None:
    s = await make_sanatorium(db, slug="prog-inv-2")
    # Bundled (no price/currency) program — set up directly.
    program = TreatmentProgram(
        sanatorium_id=s.id,
        name={"en": "Bundled detox"},
        description={},
        min_nights=3,
        instructor_bio={},
        what_to_bring={},
    )
    db.add(program)
    await db.commit()
    await db.refresh(program)
    headers = await _super_headers(client, db)
    resp = await client.patch(
        f"/api/programs/{program.id}",
        json={"currency": "USD"},
        headers=headers,
    )
    assert resp.status_code == 400


async def test_patch_both_price_and_currency_accepted(
    client: AsyncClient, db: AsyncSession
) -> None:
    s = await make_sanatorium(db, slug="prog-inv-3")
    program = await _bookable_program(db, sanatorium_id=s.id)
    headers = await _super_headers(client, db)
    resp = await client.patch(
        f"/api/programs/{program.id}",
        json={"price": "60.00", "currency": "USD"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["price"] == "60.00"


async def test_patch_clearing_both_accepted(
    client: AsyncClient, db: AsyncSession
) -> None:
    s = await make_sanatorium(db, slug="prog-inv-4")
    program = await _bookable_program(db, sanatorium_id=s.id)
    headers = await _super_headers(client, db)
    resp = await client.patch(
        f"/api/programs/{program.id}",
        json={"price": None, "currency": None},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["price"] is None
    assert resp.json()["currency"] is None
