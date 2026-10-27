from app.models.amenity import AmenityCost, AmenityScope, AmenitySelectionStatus
from app.core.meta.shared import Label, Option, from_enum, from_labels


_AMENITY_SCOPE: dict[str, Label] = {
    "sanatorium": {"uz": "Sanatoriya", "ru": "Санаторий", "en": "Sanatorium"},
    "room": {"uz": "Xona", "ru": "Номер", "en": "Room"},
    "both": {"uz": "Ikkalasi", "ru": "Оба", "en": "Both"},
}

_AMENITY_STATUS: dict[str, Label] = {
    "yes": {"uz": "Ha", "ru": "Да", "en": "Yes"},
    "no": {"uz": "Yo'q", "ru": "Нет", "en": "No"},
    "not_specified": {
        "uz": "Ko'rsatilmagan",
        "ru": "Не указано",
        "en": "Not specified",
    },
}

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
    "business": {"uz": "Biznes", "ru": "Бизнес", "en": "Business"},
    "connectivity": {"uz": "Aloqa", "ru": "Связь", "en": "Connectivity"},
    "family": {"uz": "Oila uchun", "ru": "Для семьи", "en": "Family"},
    "food": {"uz": "Ovqatlanish", "ru": "Питание", "en": "Food"},
    "health_and_wellness": {
        "uz": "Sog'liq va wellness",
        "ru": "Здоровье и велнес",
        "en": "Health and wellness",
    },
    "location": {"uz": "Joylashuv", "ru": "Расположение", "en": "Location"},
    "sport": {"uz": "Sport", "ru": "Спорт", "en": "Sport"},
    "room": {"uz": "Xona", "ru": "Номер", "en": "Room"},
    "bathroom": {"uz": "Hammom", "ru": "Ванная комната", "en": "Bathroom"},
    "kitchen": {"uz": "Oshxona", "ru": "Кухня", "en": "Kitchen"},
    "media": {"uz": "Media", "ru": "Медиа", "en": "Media"},
    "room_layout": {
        "uz": "Xona rejasi",
        "ru": "Планировка номера",
        "en": "Room layout",
    },
}


def amenity_meta() -> dict[str, list[Option]]:
    return {
        "amenity_scopes": from_enum(AmenityScope, _AMENITY_SCOPE),
        "amenity_statuses": from_enum(AmenitySelectionStatus, _AMENITY_STATUS),
        "amenity_costs": from_enum(AmenityCost, _AMENITY_COST),
        "amenity_categories": from_labels(_AMENITY_CATEGORY),
    }
