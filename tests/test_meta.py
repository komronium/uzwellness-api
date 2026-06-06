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
    assert {"featured", "dining", "leisure", "public_area", "other"} <= _values(
        body["image_categories"]
    )
    assert {"deal", "trust", "benefit", "info"} <= _values(body["promo_badge_kinds"])
    assert {"private_host", "professional_host"} == _values(body["host_types"])
    assert {"standard", "flexible", "children_as_adults"} == _values(
        body["child_rate_modes"]
    )
    assert {"free", "same_as_adults", "fixed"} == _values(body["child_pricing_methods"])
    assert {"buffet", "a_la_carte", "set_menu", "box", "no_information"} == _values(
        body["breakfast_serving_styles"]
    )
    assert {"per_stay", "per_day", "per_pet_per_day"} == _values(
        body["pet_fee_frequencies"]
    )
    assert {"fixed", "percent", "first_night"} == _values(body["deposit_types"])
    assert {"cash", "card", "bank_transfer"} == _values(
        body["payment_guarantee_methods"]
    )
    assert {"tax_inclusive", "tax_exclusive"} == _values(body["tax_pricing_modes"])
    assert {"vat", "tourism_tax", "custom"} <= _values(body["tax_fee_types"])
    assert {"property", "room"} == _values(body["tax_fee_levels"])
    assert {
        "per_room_per_night_percent",
        "per_person_per_night_fixed",
        "per_booking_fixed",
    } <= _values(body["tax_fee_calculation_methods"])
    assert {"popular_facilities", "health_wellness", "sport_fitness"} <= _values(
        body["facility_service_groups"]
    )
    assert {"hotel_room", "shared_room_bed"} == _values(body["accommodation_types"])
    assert {"male_only", "female_only"} == _values(body["gender_restrictions"])
    assert {"same_size", "different_sizes"} == _values(body["room_size_policies"])
    assert {"non_smoking", "smoking_permitted", "some_smoking"} == _values(
        body["smoking_policies"]
    )
    assert {
        "all_rooms_have_windows",
        "some_rooms_have_windows",
        "no_rooms_have_windows",
    } == _values(body["window_policies"])
    assert {"popular_amenities", "bathroom", "media_technology"} <= _values(
        body["room_amenity_groups"]
    )
    assert {"yes", "no", "not_specified"} == _values(body["amenity_statuses"])
    assert {"sanatorium", "room", "both"} == _values(body["amenity_scopes"])
    assert {"adult", "child"} == _values(body["stay_option_guest_types"])
    assert {"treatment", "special"} == _values(body["room_offer_package_kinds"])
    assert {
        "full_board_and_treatment",
        "half_board_and_treatment",
        "full_board_without_treatment",
        "half_board_without_treatment",
    } == _values(body["room_guest_option_presets"])


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
    assert {
        "room_status_restrictions",
        "inventory",
        "rate",
        "max_rooms_available",
        "cancellation_policy",
        "bulk_operation",
    } == _values(body["availability_log_categories"])
    assert {
        "mobile_rate",
        "basic_deal",
        "early_bird",
        "last_minute",
        "long_stay",
        "seasonal",
        "member",
        "package",
        "custom",
    } == _values(body["promotion_categories"])
    assert {"active", "paused", "inactive"} == _values(body["promotion_statuses"])
    assert {"all_guests"} == _values(body["promotion_audiences"])
    assert {"original", "custom"} == _values(
        body["promotion_cancellation_policy_modes"]
    )
    assert {"uzwellness", "trip_com", "qunar", "ly_com"} <= _values(
        body["review_sources"]
    )
    assert {"awaiting_reply", "replied", "not_required"} == _values(
        body["review_reply_statuses"]
    )
    assert {"none", "submitted", "approved", "rejected"} == _values(
        body["review_appeal_statuses"]
    )
    assert {"-created_at", "created_at", "-rating", "rating"} == _values(
        body["review_sort_options"]
    )
