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
    assert {"medical", "children", "sport"} <= _values(body["stay_program_categories"])
    assert {
        "doctor_observation",
        "hydrotherapy",
        "ozonotherapy",
        "sauna_once",
    } <= _values(body["stay_program_inclusions"])
    assert {"meals", "extra_mattress", "bedding"} <= _values(body["policy_includes"])


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
    assert {"deal", "trust", "benefit", "info"} <= _values(body["promo_badge_kinds"])


async def test_meta_contains_admin_reservation_and_availability_labels(
    client: AsyncClient,
) -> None:
    resp = await client.get("/api/meta")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert {"booking_date", "check_in", "check_out"} == _values(
        body["booking_date_filters"]
    )
    assert {str(day) for day in range(7)} == _values(body["weekdays"])
    assert {"4", "5"} == _values(body["weekend_days"])
    assert {
        "min_advance_hours",
        "max_advance_hours",
        "min_stay_nights",
        "min_stay_arrival_nights",
    } == _values(body["bulk_restriction_fields"])
    assert {"day_of_week", "date_order", "custom_range"} == _values(
        body["copy_rate_alignments"]
    )
    assert {"none", "increase_percent", "decrease_percent"} == _values(
        body["copy_rate_adjustments"]
    )
    assert {"email", "phone", "sms"} == _values(
        body["reservation_fallback_processing_methods"]
    )
    assert {"bookable", "unbookable"} == _values(body["availability_room_statuses"])
