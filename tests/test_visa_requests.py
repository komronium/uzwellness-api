import uuid
from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import UserRole
from tests.factories import InMemoryStorage, make_png, make_user

PNG = make_png()
PDF = b"%PDF-1.4\n%fake-pdf\n"

_ARRIVAL = (date.today() + timedelta(days=60)).isoformat()
_DEPART = (date.today() + timedelta(days=70)).isoformat()
_BIRTH = "1990-01-15"

PAYLOAD = {
    "full_name": "John Doe",
    "citizenship": "United Kingdom",
    "passport_number": "AB1234567",
    "date_of_birth": _BIRTH,
    "arrival_date": _ARRIVAL,
    "departure_date": _DEPART,
    "purpose": "treatment",
    "contact_email": "john@example.com",
    "contact_phone": "+44 7700 900000",
}


# ── create ─────────────────────────────────────────────────────────────────


async def test_customer_creates_visa_request(
    client: AsyncClient, customer_user, customer_headers
) -> None:
    resp = await client.post(
        "/api/visa-requests", json=PAYLOAD, headers=customer_headers
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["user_id"] == str(customer_user.id)
    assert body["full_name"] == "John Doe"
    assert body["purpose"] == "treatment"


async def test_anonymous_cannot_create(client: AsyncClient) -> None:
    resp = await client.post("/api/visa-requests", json=PAYLOAD)
    assert resp.status_code == 401


async def test_departure_before_arrival_returns_422(
    client: AsyncClient, customer_headers
) -> None:
    bad = {**PAYLOAD, "departure_date": _ARRIVAL, "arrival_date": _DEPART}
    resp = await client.post(
        "/api/visa-requests", json=bad, headers=customer_headers
    )
    assert resp.status_code == 422


# ── list / get visibility ──────────────────────────────────────────────────


async def test_customer_sees_only_own_visa_requests(
    client: AsyncClient,
    db: AsyncSession,
    customer_user,
    customer_headers,
) -> None:
    other = await make_user(
        db, email="other-cust@test.com", role=UserRole.CUSTOMER
    )
    other_login = await client.post(
        "/api/auth/login",
        json={"email": other.email, "password": "passw0rd"},
    )
    other_headers = {
        "Authorization": f"Bearer {other_login.json()['access_token']}"
    }
    await client.post("/api/visa-requests", json=PAYLOAD, headers=customer_headers)
    await client.post("/api/visa-requests", json=PAYLOAD, headers=other_headers)

    me = await client.get("/api/visa-requests", headers=customer_headers)
    assert me.json()["total"] == 1
    assert me.json()["items"][0]["user_id"] == str(customer_user.id)


async def test_super_admin_sees_all_visa_requests(
    client: AsyncClient, customer_headers, super_admin_headers
) -> None:
    await client.post("/api/visa-requests", json=PAYLOAD, headers=customer_headers)
    await client.post("/api/visa-requests", json=PAYLOAD, headers=customer_headers)
    resp = await client.get("/api/visa-requests", headers=super_admin_headers)
    assert resp.json()["total"] == 2


async def test_customer_cannot_view_others_visa_request(
    client: AsyncClient,
    db: AsyncSession,
    customer_headers,
) -> None:
    # Create the visa as one customer
    created = await client.post(
        "/api/visa-requests", json=PAYLOAD, headers=customer_headers
    )
    visa_id = created.json()["id"]

    # Switch to a different customer
    other = await make_user(
        db, email="snoop@test.com", role=UserRole.CUSTOMER
    )
    other_login = await client.post(
        "/api/auth/login",
        json={"email": other.email, "password": "passw0rd"},
    )
    other_headers = {
        "Authorization": f"Bearer {other_login.json()['access_token']}"
    }
    resp = await client.get(
        f"/api/visa-requests/{visa_id}", headers=other_headers
    )
    assert resp.status_code == 404


# ── status update ──────────────────────────────────────────────────────────


async def test_super_admin_updates_status(
    client: AsyncClient, customer_headers, super_admin_headers
) -> None:
    created = await client.post(
        "/api/visa-requests", json=PAYLOAD, headers=customer_headers
    )
    visa_id = created.json()["id"]
    resp = await client.patch(
        f"/api/visa-requests/{visa_id}/status",
        json={"status": "processing", "admin_notes": "Documents received"},
        headers=super_admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "processing"
    assert body["admin_notes"] == "Documents received"


async def test_customer_cannot_update_status(
    client: AsyncClient, customer_headers
) -> None:
    created = await client.post(
        "/api/visa-requests", json=PAYLOAD, headers=customer_headers
    )
    visa_id = created.json()["id"]
    resp = await client.patch(
        f"/api/visa-requests/{visa_id}/status",
        json={"status": "issued"},
        headers=customer_headers,
    )
    assert resp.status_code == 403


# ── uploads ────────────────────────────────────────────────────────────────


async def test_customer_uploads_passport_scan(
    client: AsyncClient,
    customer_headers,
    storage: InMemoryStorage,
) -> None:
    created = await client.post(
        "/api/visa-requests", json=PAYLOAD, headers=customer_headers
    )
    visa_id = created.json()["id"]
    resp = await client.post(
        f"/api/visa-requests/{visa_id}/upload-passport",
        files={"file": ("passport.png", PNG, "image/png")},
        headers=customer_headers,
    )
    assert resp.status_code == 200, resp.text
    url = resp.json()["passport_scan_url"]
    assert url is not None
    key = url.removeprefix(storage.url_prefix + "/")
    assert key in storage.objects
    assert storage.objects[key] == PNG


async def test_passport_upload_accepts_pdf(
    client: AsyncClient,
    customer_headers,
    storage: InMemoryStorage,
) -> None:
    created = await client.post(
        "/api/visa-requests", json=PAYLOAD, headers=customer_headers
    )
    visa_id = created.json()["id"]
    resp = await client.post(
        f"/api/visa-requests/{visa_id}/upload-passport",
        files={"file": ("passport.pdf", PDF, "application/pdf")},
        headers=customer_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["passport_scan_url"].endswith(".pdf")


async def test_passport_upload_rejects_unknown_type(
    client: AsyncClient, customer_headers
) -> None:
    created = await client.post(
        "/api/visa-requests", json=PAYLOAD, headers=customer_headers
    )
    visa_id = created.json()["id"]
    resp = await client.post(
        f"/api/visa-requests/{visa_id}/upload-passport",
        files={"file": ("evil.txt", b"plain text", "text/plain")},
        headers=customer_headers,
    )
    assert resp.status_code == 415


async def test_customer_cannot_upload_to_others_visa(
    client: AsyncClient, db: AsyncSession, customer_headers
) -> None:
    created = await client.post(
        "/api/visa-requests", json=PAYLOAD, headers=customer_headers
    )
    visa_id = created.json()["id"]
    other = await make_user(
        db, email="snoop2@test.com", role=UserRole.CUSTOMER
    )
    other_login = await client.post(
        "/api/auth/login",
        json={"email": other.email, "password": "passw0rd"},
    )
    other_headers = {
        "Authorization": f"Bearer {other_login.json()['access_token']}"
    }
    resp = await client.post(
        f"/api/visa-requests/{visa_id}/upload-passport",
        files={"file": ("p.png", PNG, "image/png")},
        headers=other_headers,
    )
    assert resp.status_code == 404


async def test_super_admin_uploads_issued_document(
    client: AsyncClient,
    customer_headers,
    super_admin_headers,
    storage: InMemoryStorage,
) -> None:
    created = await client.post(
        "/api/visa-requests", json=PAYLOAD, headers=customer_headers
    )
    visa_id = created.json()["id"]
    resp = await client.post(
        f"/api/visa-requests/{visa_id}/upload-document",
        files={"file": ("visa.pdf", PDF, "application/pdf")},
        headers=super_admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["issued_document_url"].endswith(".pdf")


async def test_customer_cannot_upload_issued_document(
    client: AsyncClient, customer_headers
) -> None:
    created = await client.post(
        "/api/visa-requests", json=PAYLOAD, headers=customer_headers
    )
    visa_id = created.json()["id"]
    resp = await client.post(
        f"/api/visa-requests/{visa_id}/upload-document",
        files={"file": ("visa.pdf", PDF, "application/pdf")},
        headers=customer_headers,
    )
    assert resp.status_code == 403


# ── 404 ────────────────────────────────────────────────────────────────────


async def test_status_update_on_unknown_visa_returns_404(
    client: AsyncClient, super_admin_headers
) -> None:
    resp = await client.patch(
        f"/api/visa-requests/{uuid.uuid4()}/status",
        json={"status": "issued"},
        headers=super_admin_headers,
    )
    assert resp.status_code == 404
