from app.schemas.sanatorium_medical import MedicalBaseRead
from app.schemas.sanatorium import _meal_schedule, _phones, _surroundings


def test_medical_base_read_accepts_legacy_procedure_list() -> None:
    data = {
        "description": {"en": "Medical base"},
        "natural_resources": ["mineral_water"],
        "procedures": [
            {
                "code": "mineral_bath",
                "description": {"en": "Mineral bath"},
            }
        ],
    }

    result = MedicalBaseRead.from_obj(data, "en")

    assert result.description == "Medical base"
    assert result.procedures["general"][0].code == "mineral_bath"


def test_medical_base_read_ignores_invalid_procedure_shape() -> None:
    data = {
        "description": {"en": "Medical base"},
        "procedures": "invalid",
    }

    result = MedicalBaseRead.from_obj(data, "en")

    assert result.procedures == {}


def test_public_sanatorium_helpers_normalize_legacy_contact_and_detail_json() -> None:
    assert _phones(
        [
            {"label": "Reception", "phone": "+998 69 433 10 00"},
            "+998 90 213 10 00",
        ]
    ) == ["+998 69 433 10 00", "+998 90 213 10 00"]

    assert _surroundings(
        [
            {
                "name": "Namangan city",
                "type": "city",
                "distance": "approx. 25 km",
            }
        ]
    ) == [{"name": "Namangan city", "type": "city", "distance_m": 25000}]

    assert _meal_schedule(
        [{"name": "Breakfast", "time": "08:00-09:30", "board": "all"}]
    ) == [
        {
            "meal": "breakfast",
            "time_from": "08:00",
            "time_to": "09:30",
            "style": "all",
        }
    ]
