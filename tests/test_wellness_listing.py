"""Tests for property_type / wellness_category filters on /sanatoriums."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sanatorium import PropertyType, SanatoriumStatus, WellnessCategory
from tests.factories import make_sanatorium


async def _mk(
    db, *, slug, property_type, wellness_category=None, treatment_focuses=None
):
    s = await make_sanatorium(db, slug=slug, status=SanatoriumStatus.APPROVED)
    s.property_type = property_type
    s.wellness_category = wellness_category
    s.treatment_focuses = treatment_focuses or []
    await db.commit()
    return s


class TestPropertyTypeFilter:
    async def test_filter_sanatorium_only(self, client: AsyncClient, db: AsyncSession):
        await _mk(db, slug="sanat-1", property_type=PropertyType.SANATORIUM)
        await _mk(
            db,
            slug="wellness-1",
            property_type=PropertyType.WELLNESS,
            wellness_category=WellnessCategory.SPA_RESORT,
        )
        resp = await client.get("/api/sanatoriums?property_type=sanatorium")
        slugs = {item["slug"] for item in resp.json()["items"]}
        assert slugs == {"sanat-1"}

    async def test_filter_wellness_only(self, client: AsyncClient, db: AsyncSession):
        await _mk(db, slug="sanat-2", property_type=PropertyType.SANATORIUM)
        await _mk(
            db,
            slug="wellness-2",
            property_type=PropertyType.WELLNESS,
            wellness_category=WellnessCategory.YOGA_RETREAT,
        )
        resp = await client.get("/api/sanatoriums?property_type=wellness")
        slugs = {item["slug"] for item in resp.json()["items"]}
        assert slugs == {"wellness-2"}


class TestWellnessCategoryFilter:
    async def test_filter_yoga_retreat(self, client: AsyncClient, db: AsyncSession):
        await _mk(
            db,
            slug="yoga",
            property_type=PropertyType.WELLNESS,
            wellness_category=WellnessCategory.YOGA_RETREAT,
        )
        await _mk(
            db,
            slug="spa",
            property_type=PropertyType.WELLNESS,
            wellness_category=WellnessCategory.SPA_RESORT,
        )
        resp = await client.get("/api/sanatoriums?wellness_category=yoga_retreat")
        slugs = {item["slug"] for item in resp.json()["items"]}
        assert slugs == {"yoga"}


class TestTreatmentFocusFilter:
    async def test_filter_by_focus_array_contains(
        self, client: AsyncClient, db: AsyncSession
    ):
        await _mk(
            db,
            slug="cardio",
            property_type=PropertyType.SANATORIUM,
            treatment_focuses=["cardiology", "neurology"],
        )
        await _mk(
            db,
            slug="dermo",
            property_type=PropertyType.SANATORIUM,
            treatment_focuses=["dermatology"],
        )
        resp = await client.get("/api/sanatoriums?treatment_focus=cardiology")
        slugs = {item["slug"] for item in resp.json()["items"]}
        assert slugs == {"cardio"}
