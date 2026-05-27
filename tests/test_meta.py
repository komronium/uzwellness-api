from httpx import AsyncClient


def _values(options: list[dict]) -> set[str]:
    return {item["value"] for item in options}


async def test_meta_contains_humson_duration_and_policy_labels(
    client: AsyncClient,
) -> None:
    resp = await client.get("/api/meta")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert {"1_4", "5", "7", "10"} <= _values(body["stay_durations"])
    assert {"medical", "children", "sport"} <= _values(
        body["stay_program_categories"]
    )
    assert {
        "doctor_observation",
        "hydrotherapy",
        "ozonotherapy",
        "sauna_once",
    } <= _values(body["stay_program_inclusions"])
    assert {"meals", "extra_mattress", "bedding"} <= _values(
        body["policy_includes"]
    )


async def test_meta_contains_demo_medical_and_media_labels(
    client: AsyncClient,
) -> None:
    resp = await client.get("/api/meta")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert {"mountain_air", "spring_water", "forest_zone"} <= _values(
        body["natural_resources"]
    )
    assert {
        "sharko_shower",
        "colon_hydrotherapy",
        "medical_hydromassage_bath",
        "mechanomassage",
        "infrared",
    } <= _values(body["medical_procedures"])
    assert {"exterior", "treatment", "bedroom", "tour"} <= _values(
        body["image_categories"]
    )
    assert {"deal", "trust", "benefit", "info"} <= _values(
        body["promo_badge_kinds"]
    )
