from collections import Counter

from scripts.translate_catalog_content import patch, translate


def test_exact_and_pattern_translations() -> None:
    assert translate("Full board and treatment") == (
        "To'liq pansion va davolash",
        "Полный пансион и лечение",
    )
    assert translate("Comfort Twin at Zomin Sanatorium") == (
        "Zomin sanatoriyasidagi Komfort Twin (2 ta alohida karavot)",
        "Комфорт Twin (2 отдельные кровати) в санатории Зомин",
    )
    assert translate("Chimyon Sanatorium photo 2") == (
        "Chimyon sanatoriyasi — 2-rasm",
        "Санаторий Чимион — фото 2",
    )
    assert translate("nimadir") is None


def test_fills_only_copies_of_english_and_never_overwrites_admin_text() -> None:
    stats, missing = Counter(), Counter()
    value = {
        "name": {"en": "Neurology", "uz": "Neurology", "ru": "Нейрология (админ)"},
        "nested": [{"title": {"en": "Dining hall", "uz": "", "ru": None}}],
    }

    patched = patch(value, stats, missing)

    assert patched["name"] == {
        "en": "Neurology",
        "uz": "Nevrologiya",
        "ru": "Нейрология (админ)",  # an admin's own text survives
    }
    assert patched["nested"][0]["title"] == {
        "en": "Dining hall",
        "uz": "Ovqatlanish zali",
        "ru": "Обеденный зал",
    }
    assert value["name"]["uz"] == "Neurology"  # input is not mutated
    assert stats["filled"] == 3


def test_reports_strings_it_cannot_translate() -> None:
    stats, missing = Counter(), Counter()

    patch({"en": "Test Room", "uz": "Test Room", "ru": "Test Room"}, stats, missing)

    assert missing == Counter({"Test Room": 1})
    assert stats["filled"] == 0
