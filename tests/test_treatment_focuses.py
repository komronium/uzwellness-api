from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.program import TreatmentFocus, TreatmentProgram
from app.models.sanatorium import SanatoriumStatus
from tests.factories import make_png, make_sanatorium

PNG = make_png()


async def _make_focus(
    db: AsyncSession,
    *,
    slug: str,
    name_en: str,
    is_active: bool = True,
    display_order: int = 0,
) -> TreatmentFocus:
    focus = TreatmentFocus(
        slug=slug,
        name={"en": name_en, "uz": name_en, "ru": name_en},
        description={"en": f"{name_en} description"},
        icon="activity",
        image_url=f"/uploads/demo/treatment-focuses/{slug}.jpg",
        display_order=display_order,
        is_active=is_active,
    )
    db.add(focus)
    await db.commit()
    await db.refresh(focus)
    return focus


async def _make_program(
    db: AsyncSession,
    *,
    focus: TreatmentFocus,
    status: SanatoriumStatus = SanatoriumStatus.APPROVED,
    is_active: bool = True,
) -> TreatmentProgram:
    active_label = "active" if is_active else "inactive"
    sanatorium = await make_sanatorium(
        db, status=status, slug=f"{focus.slug}-{status}-{active_label}"
    )
    program = TreatmentProgram(
        sanatorium_id=sanatorium.id,
        focus_id=focus.id,
        name={"en": "Program"},
        description={"en": "Program description"},
        is_active=is_active,
    )
    db.add(program)
    await db.commit()
    await db.refresh(program)
    return program


async def test_public_treatment_focus_tiles_count_active_approved_programs(
    client: AsyncClient, db: AsyncSession
) -> None:
    cardio = await _make_focus(
        db, slug="cardiovascular", name_en="Cardiovascular care", display_order=2
    )
    digestive = await _make_focus(
        db, slug="digestive", name_en="Digestive health", display_order=1
    )
    inactive_focus = await _make_focus(
        db, slug="inactive", name_en="Inactive", is_active=False
    )
    await _make_program(db, focus=cardio)
    await _make_program(db, focus=cardio, is_active=False)
    await _make_program(db, focus=cardio, status=SanatoriumStatus.REJECTED)
    await _make_program(db, focus=digestive)
    await _make_program(db, focus=inactive_focus)

    resp = await client.get("/api/treatment-focuses/tiles")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    assert [item["slug"] for item in body["items"]] == ["digestive", "cardiovascular"]
    digestive_item = body["items"][0]
    cardio_item = body["items"][1]
    assert digestive_item["programs_count"] == 1
    assert digestive_item["sanatoriums_count"] == 1
    assert cardio_item["programs_count"] == 1
    assert cardio_item["sanatoriums_count"] == 1


async def test_public_list_hides_inactive_treatment_focuses(
    client: AsyncClient, db: AsyncSession
) -> None:
    await _make_focus(db, slug="active", name_en="Active")
    await _make_focus(db, slug="inactive", name_en="Inactive", is_active=False)

    resp = await client.get("/api/treatment-focuses?active_only=false")

    assert resp.status_code == 200, resp.text
    assert [item["slug"] for item in resp.json()["items"]] == ["active"]


async def test_super_admin_can_create_treatment_focus(
    client: AsyncClient, super_admin_headers
) -> None:
    resp = await client.post(
        "/api/treatment-focuses",
        headers=super_admin_headers,
        json={
            "slug": "respiratory",
            "name": {
                "uz": "Nafas terapiyasi",
                "ru": "Респираторная терапия",
                "en": "Respiratory therapy",
            },
            "description": {"en": "Lung and breathing programs"},
            "icon": "lungs",
            "display_order": 3,
        },
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["slug"] == "respiratory"
    assert body["name"]["en"] == "Respiratory therapy"
    assert body["image_url"] is None


async def test_customer_cannot_create_treatment_focus(
    client: AsyncClient, customer_headers
) -> None:
    resp = await client.post(
        "/api/treatment-focuses",
        headers=customer_headers,
        json={
            "name": {"uz": "x", "ru": "x", "en": "x"},
            "description": {},
        },
    )

    assert resp.status_code == 403


async def test_upload_treatment_focus_image_as_super_admin(
    client: AsyncClient, db: AsyncSession, super_admin_headers, storage
) -> None:
    focus = await _make_focus(db, slug="image", name_en="Image")

    resp = await client.post(
        f"/api/treatment-focuses/{focus.id}/image",
        headers=super_admin_headers,
        files={"file": ("focus.png", PNG, "image/png")},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["image_url"].endswith(".png")
    key = body["image_url"].removeprefix(storage.url_prefix + "/")
    assert key in storage.objects
    assert storage.objects[key] == PNG


async def test_program_create_accepts_focus_id(
    client: AsyncClient, db: AsyncSession, admin_user, admin_headers
) -> None:
    focus = await _make_focus(db, slug="musculoskeletal", name_en="Musculoskeletal")
    sanatorium = await make_sanatorium(
        db, status=SanatoriumStatus.APPROVED, admin_user_id=admin_user.id
    )

    resp = await client.post(
        "/api/programs",
        headers=admin_headers,
        json={
            "sanatorium_id": str(sanatorium.id),
            "focus_id": str(focus.id),
            "name": {"uz": "Dastur", "ru": "Программа", "en": "Program"},
            "description": {"uz": "Tavsif", "ru": "Описание", "en": "Description"},
        },
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["focus_id"] == str(focus.id)
