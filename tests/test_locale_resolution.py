"""Tests for the get_locale dependency: ?lang= > Accept-Language > default."""
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import make_sanatorium


async def _seed_trilingual(db: AsyncSession) -> None:
    await make_sanatorium(
        db,
        name={"uz": "Vodiy", "ru": "Долина", "en": "Valley"},
        slug="trilingual",
    )


async def test_default_locale_returns_english(
    client: AsyncClient, db: AsyncSession
) -> None:
    await _seed_trilingual(db)
    resp = await client.get("/api/sanatoriums")
    assert resp.json()["items"][0]["name"] == "Valley"


async def test_lang_query_overrides_default(
    client: AsyncClient, db: AsyncSession
) -> None:
    await _seed_trilingual(db)
    resp = await client.get("/api/sanatoriums?lang=ru")
    assert resp.json()["items"][0]["name"] == "Долина"


async def test_lang_query_overrides_accept_language(
    client: AsyncClient, db: AsyncSession
) -> None:
    await _seed_trilingual(db)
    resp = await client.get(
        "/api/sanatoriums?lang=uz", headers={"Accept-Language": "ru"}
    )
    assert resp.json()["items"][0]["name"] == "Vodiy"


async def test_accept_language_used_when_no_query(
    client: AsyncClient, db: AsyncSession
) -> None:
    await _seed_trilingual(db)
    resp = await client.get(
        "/api/sanatoriums", headers={"Accept-Language": "ru"}
    )
    assert resp.json()["items"][0]["name"] == "Долина"


async def test_accept_language_q_values_parsed(
    client: AsyncClient, db: AsyncSession
) -> None:
    await _seed_trilingual(db)
    resp = await client.get(
        "/api/sanatoriums",
        headers={"Accept-Language": "fr-FR,ru;q=0.9,en;q=0.8"},
    )
    # fr is unsupported, ru wins as the first supported tag.
    assert resp.json()["items"][0]["name"] == "Долина"


async def test_region_subtag_stripped(
    client: AsyncClient, db: AsyncSession
) -> None:
    await _seed_trilingual(db)
    resp = await client.get(
        "/api/sanatoriums", headers={"Accept-Language": "en-US"}
    )
    assert resp.json()["items"][0]["name"] == "Valley"


async def test_unsupported_locale_falls_through_to_default(
    client: AsyncClient, db: AsyncSession
) -> None:
    await _seed_trilingual(db)
    resp = await client.get("/api/sanatoriums?lang=de")
    assert resp.json()["items"][0]["name"] == "Valley"


async def test_include_translations_returns_dict(
    client: AsyncClient, db: AsyncSession
) -> None:
    await _seed_trilingual(db)
    resp = await client.get("/api/sanatoriums?include_translations=true")
    body = resp.json()["items"][0]
    assert body["name"] == {"uz": "Vodiy", "ru": "Долина", "en": "Valley"}


async def test_pick_locale_falls_back_when_locale_missing(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Sanatorium has only uz; request en — must fall back via uz.
    await make_sanatorium(
        db, name={"uz": "Faqat Uzbek"}, slug="uz-only"
    )
    resp = await client.get("/api/sanatoriums?lang=en")
    assert resp.json()["items"][0]["name"] == "Faqat Uzbek"
