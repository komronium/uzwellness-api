import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sanatorium import SanatoriumStatus
from app.models.user import UserRole
from tests.factories import make_sanatorium, make_user

# ---------- helpers ----------


async def _login(client: AsyncClient, email: str, password: str) -> dict[str, str]:
    resp = await client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


CREATE_PAYLOAD = {
    "name": {"uz": "Vodiy Shifosi", "ru": "Долина Исцеления", "en": "Valley Healing"},
    "description": {"uz": "Eng yaxshi", "ru": "Лучший", "en": "The best"},
    "city": "Toshkent",
    "address": {"uz": "Amir Temur 12", "ru": "Амир Темур 12", "en": "Amir Temur 12"},
    "stars": 4,
}


# ---------- create ----------


async def test_create_as_super_admin_works(
    client: AsyncClient, super_admin_headers
) -> None:
    resp = await client.post(
        "/api/sanatoriums", json=CREATE_PAYLOAD, headers=super_admin_headers
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"]["uz"] == "Vodiy Shifosi"
    assert body["name"]["en"] == "Valley Healing"
    assert body["slug"] == "vodiy-shifosi"
    assert body["status"] == "pending"
    assert body["description"]["uz"] == "Eng yaxshi"
    assert body["description"]["en"] == "The best"
    assert body["description"]["ru"] == "Лучший"


async def test_create_as_admin_auto_assigns_owner(
    client: AsyncClient, admin_headers, admin_user
) -> None:
    resp = await client.post(
        "/api/sanatoriums", json=CREATE_PAYLOAD, headers=admin_headers
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["admin_user_id"] == str(admin_user.id)


async def test_create_as_customer_returns_403(
    client: AsyncClient, customer_headers
) -> None:
    resp = await client.post(
        "/api/sanatoriums", json=CREATE_PAYLOAD, headers=customer_headers
    )
    assert resp.status_code == 403


async def test_create_anonymous_returns_401(client: AsyncClient) -> None:
    resp = await client.post("/api/sanatoriums", json=CREATE_PAYLOAD)
    assert resp.status_code == 401


async def test_create_slug_collision_suffixes(
    client: AsyncClient, super_admin_headers
) -> None:
    first = await client.post(
        "/api/sanatoriums", json=CREATE_PAYLOAD, headers=super_admin_headers
    )
    second = await client.post(
        "/api/sanatoriums",
        json={
            **CREATE_PAYLOAD,
            "address": {"uz": "Other 2", "ru": "Другой 2", "en": "Other 2"},
        },
        headers=super_admin_headers,
    )
    assert first.json()["slug"] == "vodiy-shifosi"
    assert second.json()["slug"] == "vodiy-shifosi-2"


async def test_create_invalid_stars_returns_422(
    client: AsyncClient, super_admin_headers
) -> None:
    resp = await client.post(
        "/api/sanatoriums",
        json={**CREATE_PAYLOAD, "stars": 99},
        headers=super_admin_headers,
    )
    assert resp.status_code == 422


async def test_create_with_unknown_region_id_returns_400(
    client: AsyncClient, super_admin_headers
) -> None:
    bogus = str(uuid.uuid4())
    resp = await client.post(
        "/api/sanatoriums",
        json={**CREATE_PAYLOAD, "region_id": bogus},
        headers=super_admin_headers,
    )
    assert resp.status_code == 400
    assert "region_id" in resp.json()["detail"]


async def test_create_with_unknown_destination_id_returns_400(
    client: AsyncClient, super_admin_headers
) -> None:
    bogus = str(uuid.uuid4())
    resp = await client.post(
        "/api/sanatoriums",
        json={**CREATE_PAYLOAD, "destination_id": bogus},
        headers=super_admin_headers,
    )
    assert resp.status_code == 400
    assert "destination_id" in resp.json()["detail"]


# ---------- patch ----------


async def test_patch_as_super_admin(
    client: AsyncClient, db: AsyncSession, super_admin_headers
) -> None:
    sanatorium = await make_sanatorium(db, name="Old Name", slug="old-name")
    resp = await client.patch(
        f"/api/sanatoriums/{sanatorium.id}",
        json={"name": {"uz": "New Name"}, "stars": 5},
        headers=super_admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"]["uz"] == "New Name"
    assert body["slug"] == "new-name"  # auto-regenerated
    assert body["stars"] == 5


async def test_patch_as_owning_admin(
    client: AsyncClient, db: AsyncSession, admin_user, admin_headers
) -> None:
    sanatorium = await make_sanatorium(
        db, name="Owned", slug="owned", admin_user_id=admin_user.id
    )
    resp = await client.patch(
        f"/api/sanatoriums/{sanatorium.id}",
        json={"address": {"uz": "Updated 99"}},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["address"]["uz"] == "Updated 99"


async def test_patch_as_other_admin_returns_403(
    client: AsyncClient, db: AsyncSession, admin_headers
) -> None:
    other_admin = await make_user(db, email="other-admin@test.com", role=UserRole.ADMIN)
    sanatorium = await make_sanatorium(
        db, name="Other", slug="other", admin_user_id=other_admin.id
    )
    resp = await client.patch(
        f"/api/sanatoriums/{sanatorium.id}",
        json={"address": {"uz": "should not work"}},
        headers=admin_headers,
    )
    assert resp.status_code == 403


async def test_patch_as_customer_returns_403(
    client: AsyncClient, db: AsyncSession, customer_headers
) -> None:
    sanatorium = await make_sanatorium(db, slug="s1")
    resp = await client.patch(
        f"/api/sanatoriums/{sanatorium.id}",
        json={"stars": 1},
        headers=customer_headers,
    )
    assert resp.status_code == 403


async def test_patch_merges_partial_translations(
    client: AsyncClient, db: AsyncSession, super_admin_headers
) -> None:
    sanatorium = await make_sanatorium(
        db,
        slug="merge-target",
        description={"uz": "Eski uz", "ru": "Старый ru", "en": "Old en"},
    )
    resp = await client.patch(
        f"/api/sanatoriums/{sanatorium.id}",
        json={"description": {"uz": "Yangi uz"}},
        headers=super_admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["description"]
    assert body["uz"] == "Yangi uz"
    assert body["ru"] == "Старый ru"
    assert body["en"] == "Old en"


async def test_patch_translation_null_clears_single_locale(
    client: AsyncClient, db: AsyncSession, super_admin_headers
) -> None:
    sanatorium = await make_sanatorium(
        db,
        slug="clear-target",
        description={"uz": "X", "ru": "Y", "en": "Z"},
    )
    resp = await client.patch(
        f"/api/sanatoriums/{sanatorium.id}",
        json={"description": {"ru": None}},
        headers=super_admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["description"]
    assert body["uz"] == "X"
    # Sending {ru: null} drops the key entirely from the JSONB payload.
    assert "ru" not in body
    assert body["en"] == "Z"


async def test_patch_not_found_returns_404(
    client: AsyncClient, super_admin_headers
) -> None:
    resp = await client.patch(
        f"/api/sanatoriums/{uuid.uuid4()}",
        json={"stars": 3},
        headers=super_admin_headers,
    )
    assert resp.status_code == 404


# ---------- approve ----------


async def test_approve_as_super_admin(
    client: AsyncClient, db: AsyncSession, super_admin_headers
) -> None:
    sanatorium = await make_sanatorium(
        db, slug="pending-one", status=SanatoriumStatus.PENDING
    )
    resp = await client.post(
        f"/api/sanatoriums/{sanatorium.id}/approve", headers=super_admin_headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


async def test_approve_already_approved_returns_409(
    client: AsyncClient, db: AsyncSession, super_admin_headers
) -> None:
    sanatorium = await make_sanatorium(db, slug="already")
    resp = await client.post(
        f"/api/sanatoriums/{sanatorium.id}/approve", headers=super_admin_headers
    )
    assert resp.status_code == 409


async def test_approve_as_admin_returns_403(
    client: AsyncClient, db: AsyncSession, admin_headers
) -> None:
    sanatorium = await make_sanatorium(
        db, slug="needs-approval", status=SanatoriumStatus.PENDING
    )
    resp = await client.post(
        f"/api/sanatoriums/{sanatorium.id}/approve", headers=admin_headers
    )
    assert resp.status_code == 403


async def test_approve_not_found_returns_404(
    client: AsyncClient, super_admin_headers
) -> None:
    resp = await client.post(
        f"/api/sanatoriums/{uuid.uuid4()}/approve", headers=super_admin_headers
    )
    assert resp.status_code == 404


# ---------- list visibility ----------


async def test_list_public_only_approved(client: AsyncClient, db: AsyncSession) -> None:
    await make_sanatorium(db, slug="ok", status=SanatoriumStatus.APPROVED)
    await make_sanatorium(db, slug="not-ok", status=SanatoriumStatus.PENDING)
    resp = await client.get("/api/sanatoriums")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["slug"] == "ok"


async def test_list_super_admin_sees_all(
    client: AsyncClient, db: AsyncSession, super_admin_headers
) -> None:
    await make_sanatorium(db, slug="a", status=SanatoriumStatus.APPROVED)
    await make_sanatorium(db, slug="b", status=SanatoriumStatus.PENDING)
    await make_sanatorium(db, slug="c", status=SanatoriumStatus.REJECTED)
    resp = await client.get("/api/sanatoriums", headers=super_admin_headers)
    assert resp.json()["total"] == 3


async def test_list_admin_sees_approved_and_own(
    client: AsyncClient, db: AsyncSession, admin_user, admin_headers
) -> None:
    # Admin sees the public catalogue (approved properties of all owners) plus
    # their own draft/pending/rejected listings — they should never be locked
    # out of their own work even before approval.
    await make_sanatorium(
        db,
        slug="mine-pending",
        admin_user_id=admin_user.id,
        status=SanatoriumStatus.PENDING,
    )
    await make_sanatorium(db, slug="someone-else-approved")
    await make_sanatorium(
        db, slug="someone-else-pending", status=SanatoriumStatus.PENDING
    )
    resp = await client.get("/api/sanatoriums", headers=admin_headers)
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert slugs == {"mine-pending", "someone-else-approved"}


# ---------- list filters / search / sort ----------


async def test_list_filter_city(client: AsyncClient, db: AsyncSession) -> None:
    await make_sanatorium(db, slug="tash", city="Toshkent")
    await make_sanatorium(db, slug="sam", city="Samarqand")
    resp = await client.get("/api/sanatoriums?city=Samarqand")
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["city"] == "Samarqand"


async def test_list_filter_stars(client: AsyncClient, db: AsyncSession) -> None:
    await make_sanatorium(db, slug="three", stars=3)
    await make_sanatorium(db, slug="five", stars=5)
    resp = await client.get("/api/sanatoriums?stars=5")
    assert resp.json()["total"] == 1


async def test_list_filter_status_super_admin(
    client: AsyncClient, db: AsyncSession, super_admin_headers
) -> None:
    await make_sanatorium(db, slug="ok", status=SanatoriumStatus.APPROVED)
    await make_sanatorium(db, slug="wait", status=SanatoriumStatus.PENDING)
    resp = await client.get(
        "/api/sanatoriums?status=pending", headers=super_admin_headers
    )
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["status"] == "pending"


async def test_list_search_name(client: AsyncClient, db: AsyncSession) -> None:
    await make_sanatorium(db, name="Vodiy Shifosi", slug="vodiy")
    await make_sanatorium(db, name="Yangi Hayot", slug="yangi")
    resp = await client.get("/api/sanatoriums?q=vodi")
    assert resp.json()["total"] == 1
    # Public list returns name resolved to the request locale (default: en → uz fallback)
    assert resp.json()["items"][0]["name"] == "Vodiy Shifosi"


async def test_list_search_escapes_wildcards(
    client: AsyncClient, db: AsyncSession
) -> None:
    await make_sanatorium(db, name="Real Name", slug="real")
    # `%` should be literal, not match-all
    resp = await client.get("/api/sanatoriums?q=%25")
    assert resp.json()["total"] == 0


async def test_list_sort_by_name(client: AsyncClient, db: AsyncSession) -> None:
    await make_sanatorium(db, name="Charlie", slug="c")
    await make_sanatorium(db, name="Alpha", slug="a")
    await make_sanatorium(db, name="Bravo", slug="b")
    resp = await client.get("/api/sanatoriums?sort=name")
    assert [s["name"] for s in resp.json()["items"]] == ["Alpha", "Bravo", "Charlie"]


async def test_list_sort_by_name_respects_locale(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Each row alphabetizes differently per locale, so the response order
    # must reflect the requested locale.
    await make_sanatorium(
        db,
        name={"uz": "Charlie", "ru": "Bravo", "en": "Alpha"},
        slug="loc-1",
    )
    await make_sanatorium(
        db,
        name={"uz": "Bravo", "ru": "Alpha", "en": "Charlie"},
        slug="loc-2",
    )
    await make_sanatorium(
        db,
        name={"uz": "Alpha", "ru": "Charlie", "en": "Bravo"},
        slug="loc-3",
    )
    en = await client.get("/api/sanatoriums?sort=name&lang=en")
    assert [s["slug"] for s in en.json()["items"]] == ["loc-1", "loc-3", "loc-2"]

    uz = await client.get("/api/sanatoriums?sort=name&lang=uz")
    assert [s["slug"] for s in uz.json()["items"]] == ["loc-3", "loc-2", "loc-1"]

    ru = await client.get("/api/sanatoriums?sort=name&lang=ru")
    assert [s["slug"] for s in ru.json()["items"]] == ["loc-2", "loc-1", "loc-3"]


async def test_list_sort_by_stars_desc(client: AsyncClient, db: AsyncSession) -> None:
    await make_sanatorium(db, slug="s2", stars=2)
    await make_sanatorium(db, slug="s5", stars=5)
    await make_sanatorium(db, slug="s3", stars=3)
    resp = await client.get("/api/sanatoriums?sort=-stars")
    assert [s["stars"] for s in resp.json()["items"]] == [5, 3, 2]


async def test_list_invalid_sort_returns_422(client: AsyncClient) -> None:
    resp = await client.get("/api/sanatoriums?sort=banana")
    assert resp.status_code == 422


async def test_list_pagination(client: AsyncClient, db: AsyncSession) -> None:
    for i in range(5):
        await make_sanatorium(db, name=f"S {i}", slug=f"s{i}")
    resp = await client.get("/api/sanatoriums?limit=2&offset=0")
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2


# ---------- detail visibility ----------


async def test_get_public_approved(client: AsyncClient, db: AsyncSession) -> None:
    sanatorium = await make_sanatorium(db, slug="open")
    resp = await client.get(f"/api/sanatoriums/{sanatorium.id}")
    assert resp.status_code == 200
    assert resp.json()["slug"] == "open"


async def test_get_public_pending_returns_404(
    client: AsyncClient, db: AsyncSession
) -> None:
    sanatorium = await make_sanatorium(
        db, slug="hidden", status=SanatoriumStatus.PENDING
    )
    resp = await client.get(f"/api/sanatoriums/{sanatorium.id}")
    assert resp.status_code == 404


async def test_get_super_admin_pending(
    client: AsyncClient, db: AsyncSession, super_admin_headers
) -> None:
    sanatorium = await make_sanatorium(
        db, slug="pending2", status=SanatoriumStatus.PENDING
    )
    resp = await client.get(
        f"/api/sanatoriums/{sanatorium.id}", headers=super_admin_headers
    )
    assert resp.status_code == 200


async def test_get_admin_other_pending_returns_404(
    client: AsyncClient, db: AsyncSession, admin_headers
) -> None:
    other_admin = await make_user(db, email="o-admin@test.com", role=UserRole.ADMIN)
    sanatorium = await make_sanatorium(
        db,
        slug="other-pending",
        status=SanatoriumStatus.PENDING,
        admin_user_id=other_admin.id,
    )
    resp = await client.get(f"/api/sanatoriums/{sanatorium.id}", headers=admin_headers)
    assert resp.status_code == 404


# ---------- medical_base ----------


MEDICAL_BASE_PAYLOAD = {
    "description": {
        "uz": "Davolash bazasi tavsifi",
        "ru": "Описание лечебной базы",
        "en": "Medical base description",
    },
    "procedures_per_week": 10,
    "min_age_for_treatment": 4,
    "checkups_included": 2,
    "natural_resources": ["thermal_mineral_water", "mud"],
    "procedures": {
        "hydrotherapy": [
            {
                "code": "circular_shower",
                "image_url": "https://cdn.example.com/circular.jpg",
                "description": {
                    "uz": "Sirkulyar dush",
                    "ru": "Циркулярный душ",
                    "en": "Circular shower",
                },
            },
            {
                "code": "pearl_baths",
                "description": {
                    "uz": "Marvaridli vannalar",
                    "ru": "Жемчужные ванны",
                    "en": "Pearl baths",
                },
            },
        ],
        "physiotherapy": [
            {
                "code": "magnetotherapy",
                "description": {
                    "uz": "Magnitoterapiya",
                    "ru": "Магнитотерапия",
                    "en": "Magnetotherapy",
                },
            },
        ],
    },
    "stay_inclusions": [
        {"min_days": 1, "inclusions": ["meals_4x", "pool_access"]},
        {"min_days": 5, "inclusions": ["doctor_consultation", "lab_tests"]},
    ],
}


async def test_create_with_medical_base(
    client: AsyncClient, super_admin_headers
) -> None:
    resp = await client.post(
        "/api/sanatoriums",
        json={**CREATE_PAYLOAD, "medical_base": MEDICAL_BASE_PAYLOAD},
        headers=super_admin_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    mb = body["medical_base"]
    assert mb["description"]["uz"] == "Davolash bazasi tavsifi"
    assert mb["procedures_per_week"] == 10
    assert mb["min_age_for_treatment"] == 4
    assert mb["checkups_included"] == 2
    assert len(mb["natural_resources"]) == 2
    assert "hydrotherapy" in mb["procedures"]
    assert len(mb["procedures"]["hydrotherapy"]) == 2
    assert mb["procedures"]["hydrotherapy"][0]["code"] == "circular_shower"
    assert mb["procedures"]["hydrotherapy"][0]["image_url"].endswith("circular.jpg")
    assert len(mb["stay_inclusions"]) == 2


async def test_create_default_medical_base(
    client: AsyncClient, super_admin_headers
) -> None:
    resp = await client.post(
        "/api/sanatoriums", json=CREATE_PAYLOAD, headers=super_admin_headers
    )
    assert resp.status_code == 201, resp.text
    mb = resp.json()["medical_base"]
    assert mb["description"] == {"uz": None, "ru": None, "en": None}
    assert mb["procedures"] == {}
    assert mb["natural_resources"] == []
    assert mb["stay_inclusions"] == []


async def test_patch_medical_base(
    client: AsyncClient, db: AsyncSession, super_admin_headers
) -> None:
    sanatorium = await make_sanatorium(db, slug="med-base-patch")
    resp = await client.patch(
        f"/api/sanatoriums/{sanatorium.id}",
        json={"medical_base": {"checkups_included": 3}},
        headers=super_admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["medical_base"]["checkups_included"] == 3


async def test_get_medical_base_public_locale(
    client: AsyncClient, db: AsyncSession, super_admin_headers
) -> None:
    sanatorium = await make_sanatorium(db, slug="med-locale")
    await client.patch(
        f"/api/sanatoriums/{sanatorium.id}",
        json={"medical_base": MEDICAL_BASE_PAYLOAD},
        headers=super_admin_headers,
    )
    # public GET (no auth, no ?include_translations) → locale-resolved SanatoriumRead
    resp = await client.get(f"/api/sanatoriums/{sanatorium.id}?lang=uz")
    assert resp.status_code == 200, resp.text
    mb = resp.json()["medical_base"]
    assert mb["description"] == "Davolash bazasi tavsifi"
    assert mb["procedures"]["hydrotherapy"][0]["description"] == "Sirkulyar dush"
    assert mb["procedures"]["hydrotherapy"][1]["description"] == "Marvaridli vannalar"


# ---------- policies ----------


POLICIES_PAYLOAD = {
    "check_in": {
        "instructions": {
            "uz": "Pasport bilan receptionga murojaat qiling",
            "ru": "Обратитесь на ресепшен с паспортом",
            "en": "Check in at reception with your passport",
        },
        "required_documents": ["passport", "booking_confirmation"],
    },
    "children": {
        "allowed": True,
        "min_age": 2,
        "treatment_min_age": 12,
        "notes": {"uz": "Bolalar ota-ona bilan qabul qilinadi"},
    },
    "extra_bed": {
        "available": True,
        "crib_available": True,
        "price": "20.00",
        "currency": "USD",
    },
    "breakfast": {
        "included": True,
        "style": "buffet",
        "hours": "07:30-10:00",
    },
    "pets": {
        "allowed": False,
        "service_animals_allowed": True,
    },
    "cancellation": {
        "free_cancellation_until_days_before": 3,
        "penalty_percent": "50.00",
    },
    "payment": {
        "methods": ["cash", "visa"],
        "deposit_required": True,
        "deposit_percent": "20.00",
    },
    "fees": {
        "mandatory_fees": ["city_tax"],
        "optional_fees": ["parking"],
    },
}


async def test_create_with_policies(client: AsyncClient, super_admin_headers) -> None:
    resp = await client.post(
        "/api/sanatoriums",
        json={**CREATE_PAYLOAD, "policies": POLICIES_PAYLOAD},
        headers=super_admin_headers,
    )
    assert resp.status_code == 201, resp.text
    policies = resp.json()["policies"]
    assert policies["children"]["allowed"] is True
    assert policies["children"]["treatment_min_age"] == 12
    assert policies["breakfast"]["style"] == "buffet"
    assert policies["payment"]["deposit_percent"] == "20.00"


async def test_patch_policies(
    client: AsyncClient, db: AsyncSession, super_admin_headers
) -> None:
    sanatorium = await make_sanatorium(db, slug="policy-patch")
    resp = await client.patch(
        f"/api/sanatoriums/{sanatorium.id}",
        json={"policies": {"children": {"allowed": False}}},
        headers=super_admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["policies"]["children"]["allowed"] is False


# ---------- rating breakdown ----------


async def test_review_rating_breakdown_is_automatic(
    client: AsyncClient,
    db: AsyncSession,
    customer_headers,
) -> None:
    sanatorium = await make_sanatorium(db, slug="rating-breakdown")

    first = await client.post(
        f"/api/reviews/sanatoriums/{sanatorium.id}",
        json={
            "reviewer_name": "Guest One",
            "rating": 5,
            "cleanliness": 5,
            "amenities": 4,
            "location": 5,
            "service": 4,
            "treatment": 5,
            "body": "Excellent treatment and clean rooms.",
        },
        headers=customer_headers,
    )
    assert first.status_code == 201, first.text
    second = await client.post(
        f"/api/reviews/sanatoriums/{sanatorium.id}",
        json={
            "reviewer_name": "Guest Two",
            "rating": 3,
            "cleanliness": 3,
            "amenities": 2,
            "location": 4,
            "service": 3,
            "treatment": 4,
            "body": "Good location but service can improve.",
        },
        headers=customer_headers,
    )
    assert second.status_code == 201, second.text

    resp = await client.get(f"/api/sanatoriums/{sanatorium.id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["avg_rating"] == "4.00"
    assert body["review_count"] == 2
    assert body["rating_breakdown"]["cleanliness"] == "4.00"
    assert body["rating_breakdown"]["amenities"] == "3.00"
    assert body["rating_breakdown"]["location"] == "4.50"
    assert body["rating_breakdown"]["service"] == "3.50"
    assert body["rating_breakdown"]["treatment"] == "4.50"


async def test_review_visibility_recomputes_rating_breakdown(
    client: AsyncClient,
    db: AsyncSession,
    customer_headers,
    super_admin_headers,
) -> None:
    sanatorium = await make_sanatorium(db, slug="rating-visibility")
    low = await client.post(
        f"/api/reviews/sanatoriums/{sanatorium.id}",
        json={
            "reviewer_name": "Low Score",
            "rating": 1,
            "cleanliness": 1,
            "amenities": 1,
            "location": 1,
            "service": 1,
            "treatment": 1,
            "body": "This stay did not meet expectations.",
        },
        headers=customer_headers,
    )
    assert low.status_code == 201, low.text
    high = await client.post(
        f"/api/reviews/sanatoriums/{sanatorium.id}",
        json={
            "reviewer_name": "High Score",
            "rating": 5,
            "cleanliness": 5,
            "amenities": 5,
            "location": 5,
            "service": 5,
            "treatment": 5,
            "body": "Excellent stay with strong treatment quality.",
        },
        headers=customer_headers,
    )
    assert high.status_code == 201, high.text

    hide = await client.patch(
        f"/api/reviews/{low.json()['id']}/visibility",
        json={"is_visible": False},
        headers=super_admin_headers,
    )
    assert hide.status_code == 200, hide.text

    resp = await client.get(f"/api/sanatoriums/{sanatorium.id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["avg_rating"] == "5.00"
    assert body["review_count"] == 1
    assert body["rating_breakdown"]["treatment"] == "5.00"


# ---------- treatment profile ----------


TREATMENT_PROFILE_PAYLOAD = {
    "main_indications": [
        {
            "code": "digestive",
            "title": {
                "uz": "Ovqat hazm qilish tizimi",
                "ru": "Пищеварительная система",
                "en": "Digestive system",
            },
            "description": {
                "uz": "Oshqozon va ichak kasalliklari uchun",
                "ru": "Для заболеваний желудка и кишечника",
                "en": "For stomach and intestinal diseases",
            },
        }
    ],
    "additional_indications": [
        {
            "code": "respiratory",
            "title": {
                "uz": "Nafas olish tizimi",
                "ru": "Дыхательная система",
                "en": "Respiratory system",
            },
        }
    ],
    "contraindications": [
        {
            "code": "acute_infection",
            "title": {
                "uz": "O'tkir infeksiya",
                "ru": "Острая инфекция",
                "en": "Acute infection",
            },
        }
    ],
    "diagnostics": ["ecg", "lab_tests"],
    "doctor_specialties": ["therapist", "cardiologist"],
    "notes": {
        "uz": "Davolanishdan oldin shifokor ko'rigi zarur",
        "ru": "Перед лечением нужен осмотр врача",
        "en": "Doctor consultation is required before treatment",
    },
}


async def test_create_with_treatment_profile(
    client: AsyncClient, super_admin_headers
) -> None:
    resp = await client.post(
        "/api/sanatoriums",
        json={**CREATE_PAYLOAD, "treatment_profile": TREATMENT_PROFILE_PAYLOAD},
        headers=super_admin_headers,
    )
    assert resp.status_code == 201, resp.text
    profile = resp.json()["treatment_profile"]
    assert profile["main_indications"][0]["code"] == "digestive"
    assert profile["main_indications"][0]["title"]["uz"] == "Ovqat hazm qilish tizimi"
    assert profile["additional_indications"][0]["code"] == "respiratory"
    assert profile["contraindications"][0]["code"] == "acute_infection"
    assert profile["diagnostics"] == ["ecg", "lab_tests"]
    assert profile["doctor_specialties"] == ["therapist", "cardiologist"]


async def test_patch_treatment_profile(
    client: AsyncClient, db: AsyncSession, super_admin_headers
) -> None:
    sanatorium = await make_sanatorium(db, slug="treatment-profile-patch")
    resp = await client.patch(
        f"/api/sanatoriums/{sanatorium.id}",
        json={"treatment_profile": TREATMENT_PROFILE_PAYLOAD},
        headers=super_admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert (
        resp.json()["treatment_profile"]["main_indications"][0]["code"] == "digestive"
    )


async def test_get_treatment_profile_public_locale(
    client: AsyncClient, db: AsyncSession, super_admin_headers
) -> None:
    sanatorium = await make_sanatorium(db, slug="treatment-profile-locale")
    await client.patch(
        f"/api/sanatoriums/{sanatorium.id}",
        json={"treatment_profile": TREATMENT_PROFILE_PAYLOAD},
        headers=super_admin_headers,
    )
    resp = await client.get(f"/api/sanatoriums/{sanatorium.id}?lang=uz")
    assert resp.status_code == 200, resp.text
    profile = resp.json()["treatment_profile"]
    assert profile["main_indications"][0]["title"] == "Ovqat hazm qilish tizimi"
    assert profile["main_indications"][0]["description"] == (
        "Oshqozon va ichak kasalliklari uchun"
    )
    assert profile["additional_indications"][0]["title"] == "Nafas olish tizimi"
    assert profile["notes"] == "Davolanishdan oldin shifokor ko'rigi zarur"


# ---------- service matrix ----------


SERVICE_MATRIX_PAYLOAD = {
    "food_drink": {
        "title": {"uz": "Ovqatlanish", "ru": "Питание", "en": "Food & drink"},
        "items": [
            {
                "code": "breakfast",
                "title": {"uz": "Nonushta", "ru": "Завтрак", "en": "Breakfast"},
                "description": {
                    "uz": "Shved stoli",
                    "ru": "Шведский стол",
                    "en": "Buffet breakfast",
                },
                "cost": "free",
                "hours": "07:30-10:00",
                "location": "Restaurant",
                "icon": "utensils",
                "tags": ["meal", "buffet"],
            }
        ],
    },
    "medical_department": {
        "title": {
            "uz": "Tibbiy bo'lim",
            "ru": "Медицинское отделение",
            "en": "Medical department",
        },
        "items": [
            {
                "code": "doctor_hours",
                "title": {
                    "uz": "Shifokor qabul vaqti",
                    "ru": "Часы врача",
                    "en": "Doctor hours",
                },
                "cost": "free",
                "hours": "09:00-17:00",
            }
        ],
    },
    "parking": {
        "items": [
            {
                "code": "private_parking",
                "title": {
                    "uz": "Xususiy parking",
                    "ru": "Частная парковка",
                    "en": "Private parking",
                },
                "is_available": True,
                "cost": "paid",
            }
        ]
    },
    "internet": {
        "items": [
            {
                "code": "wifi",
                "title": {"uz": "Wi-Fi", "ru": "Wi-Fi", "en": "Wi-Fi"},
                "is_available": True,
                "cost": "free",
            }
        ]
    },
    "languages": ["uz", "ru", "en"],
    "notes": {
        "uz": "Xizmatlar mavsumga qarab o'zgarishi mumkin",
        "ru": "Услуги могут меняться по сезону",
        "en": "Services may vary by season",
    },
}


async def test_create_with_service_matrix(
    client: AsyncClient, super_admin_headers
) -> None:
    resp = await client.post(
        "/api/sanatoriums",
        json={**CREATE_PAYLOAD, "service_matrix": SERVICE_MATRIX_PAYLOAD},
        headers=super_admin_headers,
    )
    assert resp.status_code == 201, resp.text
    matrix = resp.json()["service_matrix"]
    assert matrix["food_drink"]["items"][0]["code"] == "breakfast"
    assert matrix["food_drink"]["items"][0]["cost"] == "free"
    assert matrix["medical_department"]["items"][0]["hours"] == "09:00-17:00"
    assert matrix["parking"]["items"][0]["cost"] == "paid"
    assert matrix["languages"] == ["uz", "ru", "en"]


async def test_patch_service_matrix(
    client: AsyncClient, db: AsyncSession, super_admin_headers
) -> None:
    sanatorium = await make_sanatorium(db, slug="service-matrix-patch")
    resp = await client.patch(
        f"/api/sanatoriums/{sanatorium.id}",
        json={"service_matrix": SERVICE_MATRIX_PAYLOAD},
        headers=super_admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["service_matrix"]["internet"]["items"][0]["code"] == "wifi"


async def test_get_service_matrix_public_locale(
    client: AsyncClient, db: AsyncSession, super_admin_headers
) -> None:
    sanatorium = await make_sanatorium(db, slug="service-matrix-locale")
    await client.patch(
        f"/api/sanatoriums/{sanatorium.id}",
        json={"service_matrix": SERVICE_MATRIX_PAYLOAD},
        headers=super_admin_headers,
    )
    resp = await client.get(f"/api/sanatoriums/{sanatorium.id}?lang=uz")
    assert resp.status_code == 200, resp.text
    matrix = resp.json()["service_matrix"]
    assert matrix["food_drink"]["title"] == "Ovqatlanish"
    assert matrix["food_drink"]["items"][0]["title"] == "Nonushta"
    assert matrix["food_drink"]["items"][0]["description"] == "Shved stoli"
    assert matrix["medical_department"]["title"] == "Tibbiy bo'lim"
    assert matrix["notes"] == "Xizmatlar mavsumga qarab o'zgarishi mumkin"


# ---------- promo badges ----------


PROMO_BADGES_PAYLOAD = [
    {
        "code": "free_transfer",
        "kind": "benefit",
        "title": {
            "uz": "Bepul transfer",
            "ru": "Бесплатный трансфер",
            "en": "Free transfer",
        },
        "description": {
            "uz": "Aeroportdan sanatoriygacha transfer",
            "ru": "Трансфер из аэропорта до санатория",
            "en": "Transfer from airport to sanatorium",
        },
        "icon": "bus",
        "priority": 1,
    },
    {
        "code": "old_inactive",
        "kind": "notice",
        "title": {"uz": "Eski aksiya", "ru": "Старая акция", "en": "Old promo"},
        "is_active": False,
        "priority": 99,
    },
]


async def test_create_with_promo_badges(
    client: AsyncClient, super_admin_headers
) -> None:
    resp = await client.post(
        "/api/sanatoriums",
        json={**CREATE_PAYLOAD, "promo_badges": PROMO_BADGES_PAYLOAD},
        headers=super_admin_headers,
    )
    assert resp.status_code == 201, resp.text
    badges = resp.json()["promo_badges"]
    assert badges[0]["code"] == "free_transfer"
    assert badges[0]["title"]["uz"] == "Bepul transfer"
    assert badges[1]["is_active"] is False


async def test_patch_promo_badges(
    client: AsyncClient, db: AsyncSession, super_admin_headers
) -> None:
    sanatorium = await make_sanatorium(db, slug="promo-badges-patch")
    resp = await client.patch(
        f"/api/sanatoriums/{sanatorium.id}",
        json={"promo_badges": PROMO_BADGES_PAYLOAD},
        headers=super_admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["promo_badges"][0]["kind"] == "benefit"


async def test_get_promo_badges_public_locale_filters_inactive(
    client: AsyncClient, db: AsyncSession, super_admin_headers
) -> None:
    sanatorium = await make_sanatorium(db, slug="promo-badges-locale")
    await client.patch(
        f"/api/sanatoriums/{sanatorium.id}",
        json={"promo_badges": PROMO_BADGES_PAYLOAD},
        headers=super_admin_headers,
    )
    resp = await client.get(f"/api/sanatoriums/{sanatorium.id}?lang=uz")
    assert resp.status_code == 200, resp.text
    badges = resp.json()["promo_badges"]
    assert len(badges) == 1
    assert badges[0]["code"] == "free_transfer"
    assert badges[0]["title"] == "Bepul transfer"
    assert badges[0]["description"] == "Aeroportdan sanatoriygacha transfer"
