from app.schemas.sanatorium_medical import MedicalBaseRead


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
