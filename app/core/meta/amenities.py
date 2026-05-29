from app.models.amenity import AmenityCost
from app.core.meta.shared import Label, Option, from_enum, from_labels


_AMENITY_COST: dict[str, Label] = {
    "free": {"uz": "Bepul", "ru": "Бесплатно", "en": "Free"},
    "paid": {
        "uz": "Qo'shimcha to'lov",
        "ru": "За дополнительную плату",
        "en": "Additional charge",
    },
    "on_request": {"uz": "So'rov bo'yicha", "ru": "По запросу", "en": "On request"},
}

_AMENITY_CATEGORY: dict[str, Label] = {
    "facility": {"uz": "Inshoot", "ru": "Объект", "en": "Facility"},
    "medical": {"uz": "Tibbiy", "ru": "Медицина", "en": "Medical"},
    "nutrition": {"uz": "Ovqatlanish", "ru": "Питание", "en": "Nutrition"},
    "wellness": {"uz": "Wellness", "ru": "Велнес", "en": "Wellness"},
    "internet": {"uz": "Internet", "ru": "Интернет", "en": "Internet"},
    "transport": {"uz": "Transport", "ru": "Транспорт", "en": "Transportation"},
    "parking": {"uz": "Parking", "ru": "Парковка", "en": "Parking"},
    "front_desk": {"uz": "Qabul", "ru": "Стойка регистрации", "en": "Front desk"},
    "cleaning": {"uz": "Tozalash", "ru": "Уборка", "en": "Cleaning"},
    "food_drink": {
        "uz": "Ovqat va ichimlik",
        "ru": "Еда и напитки",
        "en": "Food & drink",
    },
    "public_areas": {"uz": "Umumiy hududlar", "ru": "Общие зоны", "en": "Public areas"},
    "children": {"uz": "Bolalar uchun", "ru": "Для детей", "en": "For children"},
    "accessibility": {
        "uz": "Imkoniyati cheklanganlar",
        "ru": "Доступность",
        "en": "Accessibility",
    },
}


def amenity_meta() -> dict[str, list[Option]]:
    return {
        "amenity_costs": from_enum(AmenityCost, _AMENITY_COST),
        "amenity_categories": from_labels(_AMENITY_CATEGORY),
    }
