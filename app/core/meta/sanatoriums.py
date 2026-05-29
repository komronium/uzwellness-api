from app.models.sanatorium import PropertyType, WellnessCategory

from app.core.meta.medical import medical_meta
from app.core.meta.shared import Label, Option, from_enum, from_labels
from app.core.meta.stay import stay_meta


_PROPERTY_TYPE: dict[str, Label] = {
    "sanatorium": {"uz": "Sanatoriya", "ru": "Санаторий", "en": "Sanatorium"},
    "wellness": {
        "uz": "Wellness markaz",
        "ru": "Велнес-центр",
        "en": "Wellness center",
    },
}

_WELLNESS_CATEGORY: dict[str, Label] = {
    "spa_resort": {"uz": "SPA kurort", "ru": "Спа-курорт", "en": "Spa resort"},
    "yoga_retreat": {"uz": "Yoga retrit", "ru": "Йога-ретрит", "en": "Yoga retreat"},
    "meditation_center": {
        "uz": "Meditatsiya markazi",
        "ru": "Центр медитации",
        "en": "Meditation center",
    },
    "fitness_resort": {
        "uz": "Fitnes kurort",
        "ru": "Фитнес-курорт",
        "en": "Fitness resort",
    },
    "beauty_spa": {"uz": "Go'zallik SPA", "ru": "Бьюти-спа", "en": "Beauty spa"},
    "digital_detox": {
        "uz": "Raqamli deteks",
        "ru": "Цифровой детокс",
        "en": "Digital detox",
    },
}

_TREATMENT_FOCUS: dict[str, Label] = {
    "cardiovascular": {
        "uz": "Yurak-qon tomir",
        "ru": "Сердечно-сосудистые",
        "en": "Cardiovascular",
    },
    "digestive": {"uz": "Ovqat hazm qilish", "ru": "Пищеварение", "en": "Digestive"},
    "musculoskeletal": {
        "uz": "Tayanch-harakat",
        "ru": "Опорно-двигательные",
        "en": "Musculoskeletal",
    },
    "respiratory": {
        "uz": "Nafas olish",
        "ru": "Дыхательная система",
        "en": "Respiratory",
    },
    "neurological": {"uz": "Asab tizimi", "ru": "Неврология", "en": "Neurological"},
    "dermatology": {"uz": "Teri", "ru": "Дерматология", "en": "Dermatology"},
    "endocrine": {"uz": "Endokrin", "ru": "Эндокринная система", "en": "Endocrine"},
    "wellness": {"uz": "Sog'lomlashtirish", "ru": "Велнес", "en": "Wellness"},
}

_PAYMENT_METHOD: dict[str, Label] = {
    "cash": {"uz": "Naqd", "ru": "Наличные", "en": "Cash"},
    "bank_transfer": {
        "uz": "Bank o'tkazmasi",
        "ru": "Банковский перевод",
        "en": "Bank transfer",
    },
    "uzcard": {"uz": "UzCard", "ru": "UzCard", "en": "UzCard"},
    "visa": {"uz": "Visa", "ru": "Visa", "en": "Visa"},
    "mastercard": {"uz": "Mastercard", "ru": "Mastercard", "en": "Mastercard"},
    "jcb": {"uz": "JCB", "ru": "JCB", "en": "JCB"},
    "unionpay": {"uz": "UnionPay", "ru": "UnionPay", "en": "UnionPay"},
    "mir": {"uz": "Mir", "ru": "Мир", "en": "Mir"},
}

_SURROUNDING_TYPE: dict[str, Label] = {
    "attraction": {
        "uz": "Diqqatga sazovor joy",
        "ru": "Достопримечательность",
        "en": "Attraction",
    },
    "recreation": {"uz": "Dam olish", "ru": "Отдых", "en": "Recreation"},
    "transport": {"uz": "Transport", "ru": "Транспорт", "en": "Transport"},
    "shopping": {"uz": "Xarid", "ru": "Шоппинг", "en": "Shopping"},
    "dining": {"uz": "Ovqatlanish", "ru": "Рестораны", "en": "Dining"},
    "medical": {"uz": "Tibbiyot", "ru": "Медицина", "en": "Medical"},
    "landmark": {"uz": "Mashhur joy", "ru": "Ориентир", "en": "Landmark"},
}

_VENUE_TYPE: dict[str, Label] = {
    "restaurant": {"uz": "Restoran", "ru": "Ресторан", "en": "Restaurant"},
    "cafe": {"uz": "Kafe", "ru": "Кафе", "en": "Cafe"},
    "bar": {"uz": "Bar", "ru": "Бар", "en": "Bar"},
    "lobby_bar": {"uz": "Lobbi-bar", "ru": "Лобби-бар", "en": "Lobby bar"},
    "snack_bar": {"uz": "Snack-bar", "ru": "Снэк-бар", "en": "Snack bar"},
}

_MEAL_TYPE: dict[str, Label] = {
    "breakfast": {"uz": "Nonushta", "ru": "Завтрак", "en": "Breakfast"},
    "lunch": {"uz": "Tushlik", "ru": "Обед", "en": "Lunch"},
    "dinner": {"uz": "Kechki ovqat", "ru": "Ужин", "en": "Dinner"},
    "supper": {"uz": "Kechki taom", "ru": "Поздний ужин", "en": "Supper"},
    "diet_meal": {"uz": "Parhez taom", "ru": "Диетпитание", "en": "Diet meal"},
}

_IMAGE_CATEGORY: dict[str, Label] = {
    "exterior": {"uz": "Tashqi ko'rinish", "ru": "Экстерьер", "en": "Exterior"},
    "treatment": {"uz": "Davolash", "ru": "Лечение", "en": "Treatment"},
    "surroundings": {"uz": "Atrof-muhit", "ru": "Окружение", "en": "Surroundings"},
    "bedroom": {"uz": "Yotoq xona", "ru": "Спальня", "en": "Bedroom"},
    "tour": {"uz": "360 tur", "ru": "360 тур", "en": "360 tour"},
}

_PROMO_BADGE_KIND: dict[str, Label] = {
    "deal": {"uz": "Aksiya", "ru": "Акция", "en": "Deal"},
    "trust": {"uz": "Ishonch", "ru": "Доверие", "en": "Trust"},
    "benefit": {"uz": "Afzallik", "ru": "Преимущество", "en": "Benefit"},
    "info": {"uz": "Ma'lumot", "ru": "Информация", "en": "Info"},
}


def sanatorium_meta() -> dict[str, list[Option]]:
    medical = medical_meta()
    stay = stay_meta()
    return {
        "property_types": from_enum(PropertyType, _PROPERTY_TYPE),
        "wellness_categories": from_enum(WellnessCategory, _WELLNESS_CATEGORY),
        "treatment_focuses": from_labels(_TREATMENT_FOCUS),
        "payment_methods": from_labels(_PAYMENT_METHOD),
        "surrounding_types": from_labels(_SURROUNDING_TYPE),
        "venue_types": from_labels(_VENUE_TYPE),
        "meal_types": from_labels(_MEAL_TYPE),
        "natural_resources": medical["natural_resources"],
        "medical_procedure_categories": medical["medical_procedure_categories"],
        "medical_procedures": medical["medical_procedures"],
        "stay_durations": stay["stay_durations"],
        "stay_program_categories": stay["stay_program_categories"],
        "stay_program_inclusions": stay["stay_program_inclusions"],
        "policy_includes": stay["policy_includes"],
        "image_categories": from_labels(_IMAGE_CATEGORY),
        "promo_badge_kinds": from_labels(_PROMO_BADGE_KIND),
    }
