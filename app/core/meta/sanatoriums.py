from app.models.sanatorium import HostType, PropertyType, WellnessCategory

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

_HOST_TYPE: dict[str, Label] = {
    "private_host": {"uz": "Xususiy host", "ru": "Частный хост", "en": "Private host"},
    "professional_host": {
        "uz": "Professional host",
        "ru": "Профессиональный хост",
        "en": "Professional host",
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
    "featured": {
        "uz": "Asosiy rasmlar",
        "ru": "Избранные фото",
        "en": "Featured photos",
    },
    "exterior": {"uz": "Tashqi ko'rinish", "ru": "Экстерьер", "en": "Exterior"},
    "room": {"uz": "Xona", "ru": "Номер", "en": "Room"},
    "treatment": {"uz": "Davolash", "ru": "Лечение", "en": "Treatment"},
    "dining": {"uz": "Ovqatlanish", "ru": "Питание", "en": "Dining"},
    "leisure": {"uz": "Dam olish", "ru": "Досуг", "en": "Leisure"},
    "business": {"uz": "Biznes", "ru": "Бизнес", "en": "Business"},
    "family": {"uz": "Oila", "ru": "Семья", "en": "Family"},
    "public_area": {
        "uz": "Umumiy hududlar",
        "ru": "Общественные зоны",
        "en": "Public areas",
    },
    "surroundings": {"uz": "Atrof-muhit", "ru": "Окружение", "en": "Surroundings"},
    "bedroom": {"uz": "Yotoq xona", "ru": "Спальня", "en": "Bedroom"},
    "bathroom": {"uz": "Hammom", "ru": "Ванная", "en": "Bathroom"},
    "tour": {"uz": "360 tur", "ru": "360 тур", "en": "360 tour"},
    "other": {"uz": "Boshqa", "ru": "Другое", "en": "Other"},
}

_PROMO_BADGE_KIND: dict[str, Label] = {
    "deal": {"uz": "Aksiya", "ru": "Акция", "en": "Deal"},
    "trust": {"uz": "Ishonch", "ru": "Доверие", "en": "Trust"},
    "benefit": {"uz": "Afzallik", "ru": "Преимущество", "en": "Benefit"},
    "info": {"uz": "Ma'lumot", "ru": "Информация", "en": "Info"},
}

_CHILD_RATE_MODE: dict[str, Label] = {
    "standard": {"uz": "Standart", "ru": "Стандарт", "en": "Standard"},
    "flexible": {"uz": "Moslashuvchan", "ru": "Гибкий", "en": "Flexible"},
    "children_as_adults": {
        "uz": "Bolalar kattalar kabi",
        "ru": "Дети считаются взрослыми",
        "en": "Children are considered as adults",
    },
}

_CHILD_PRICING_METHOD: dict[str, Label] = {
    "free": {"uz": "Bepul", "ru": "Бесплатно", "en": "Free"},
    "same_as_adults": {
        "uz": "Kattalar bilan bir xil",
        "ru": "Как для взрослых",
        "en": "Same as adults",
    },
    "fixed": {"uz": "Belgilangan narx", "ru": "Фиксированная цена", "en": "Fixed"},
}

_BREAKFAST_SERVING_STYLE: dict[str, Label] = {
    "buffet": {"uz": "Bufet", "ru": "Шведский стол", "en": "Buffet"},
    "a_la_carte": {"uz": "A la carte", "ru": "A la carte", "en": "A la carte"},
    "set_menu": {"uz": "Set menyu", "ru": "Комплексное меню", "en": "Set menu"},
    "box": {"uz": "Qadoqlangan", "ru": "Ланч-бокс", "en": "Breakfast box"},
    "no_information": {
        "uz": "Ma'lumot yo'q",
        "ru": "Нет информации",
        "en": "No information",
    },
}

_PET_FEE_FREQUENCY: dict[str, Label] = {
    "per_stay": {"uz": "Yashash davri uchun", "ru": "За проживание", "en": "Per stay"},
    "per_day": {"uz": "Kuniga", "ru": "За день", "en": "Per day"},
    "per_pet_per_day": {
        "uz": "Har bir jonivor uchun kuniga",
        "ru": "За питомца в день",
        "en": "Per pet per day",
    },
}

_DEPOSIT_TYPE: dict[str, Label] = {
    "fixed": {"uz": "Aniq summa", "ru": "Фиксированная сумма", "en": "Fixed amount"},
    "percent": {"uz": "Foiz", "ru": "Процент", "en": "Percentage"},
    "first_night": {"uz": "Birinchi tun", "ru": "Первая ночь", "en": "First night"},
}

_PAYMENT_GUARANTEE_METHOD: dict[str, Label] = {
    "cash": {"uz": "Naqd", "ru": "Наличные", "en": "Cash"},
    "card": {"uz": "Karta", "ru": "Карта", "en": "Card"},
    "bank_transfer": {
        "uz": "Bank o'tkazmasi",
        "ru": "Банковский перевод",
        "en": "Bank transfer",
    },
}

_FACILITY_SERVICE_GROUP: dict[str, Label] = {
    "popular_facilities": {
        "uz": "Mashhur qulayliklar",
        "ru": "Популярные удобства",
        "en": "Popular facilities",
    },
    "transport": {"uz": "Transport", "ru": "Транспорт", "en": "Transport"},
    "cleaning_services": {
        "uz": "Tozalash xizmatlari",
        "ru": "Услуги уборки",
        "en": "Cleaning services",
    },
    "safety_security": {
        "uz": "Xavfsizlik",
        "ru": "Безопасность",
        "en": "Safety and security",
    },
    "recreational_activities": {
        "uz": "Dam olish mashg'ulotlari",
        "ru": "Развлечения",
        "en": "Recreational activities",
    },
    "public_areas": {
        "uz": "Umumiy hududlar",
        "ru": "Общественные зоны",
        "en": "Public areas",
    },
    "front_desk": {"uz": "Resepshen", "ru": "Стойка регистрации", "en": "Front desk"},
    "business": {"uz": "Biznes", "ru": "Бизнес", "en": "Business"},
    "amenities_for_kids": {
        "uz": "Bolalar uchun",
        "ru": "Для детей",
        "en": "Amenities for kids",
    },
    "dining": {"uz": "Ovqatlanish", "ru": "Питание", "en": "Dining"},
    "health_wellness": {
        "uz": "Sog'lomlashtirish",
        "ru": "Здоровье и велнес",
        "en": "Health and wellness",
    },
    "sport_fitness": {
        "uz": "Sport va fitnes",
        "ru": "Спорт и фитнес",
        "en": "Sport and fitness",
    },
    "accessibility": {
        "uz": "Maxsus imkoniyatlar",
        "ru": "Доступность",
        "en": "Accessibility",
    },
}

_TAX_PRICING_MODE: dict[str, Label] = {
    "tax_inclusive": {
        "uz": "Soliq narx ichida",
        "ru": "Налоги включены",
        "en": "Tax-inclusive pricing",
    },
    "tax_exclusive": {
        "uz": "Soliq narxga qo'shiladi",
        "ru": "Налоги не включены",
        "en": "Tax-exclusive pricing",
    },
}

_TAX_FEE_TYPE: dict[str, Label] = {
    "vat": {"uz": "QQS", "ru": "НДС", "en": "VAT"},
    "tourism_tax": {
        "uz": "Turizm solig'i",
        "ru": "Туристический сбор",
        "en": "Tourism tax",
    },
    "city_tax": {"uz": "Shahar solig'i", "ru": "Городской сбор", "en": "City tax"},
    "resort_fee": {"uz": "Kurort yig'imi", "ru": "Курортный сбор", "en": "Resort fee"},
    "service_fee": {"uz": "Xizmat haqi", "ru": "Сервисный сбор", "en": "Service fee"},
    "custom": {"uz": "Boshqa", "ru": "Другое", "en": "Custom"},
}

_TAX_FEE_LEVEL: dict[str, Label] = {
    "property": {"uz": "Sanatoriya", "ru": "Объект", "en": "Property"},
    "room": {"uz": "Xona", "ru": "Номер", "en": "Room"},
}

_TAX_FEE_CALCULATION_METHOD: dict[str, Label] = {
    "per_room_per_night_percent": {
        "uz": "Xona/tun bo'yicha foiz",
        "ru": "Процент за номер за ночь",
        "en": "Per room per night (%)",
    },
    "per_room_per_night_fixed": {
        "uz": "Xona/tun bo'yicha summa",
        "ru": "Фиксировано за номер за ночь",
        "en": "Per room per night (fixed)",
    },
    "per_person_per_night_percent": {
        "uz": "Mehmon/tun bo'yicha foiz",
        "ru": "Процент за гостя за ночь",
        "en": "Per person per night (%)",
    },
    "per_person_per_night_fixed": {
        "uz": "Mehmon/tun bo'yicha summa",
        "ru": "Фиксировано за гостя за ночь",
        "en": "Per person per night (fixed)",
    },
    "per_booking_percent": {
        "uz": "Bron bo'yicha foiz",
        "ru": "Процент за бронирование",
        "en": "Per booking (%)",
    },
    "per_booking_fixed": {
        "uz": "Bron bo'yicha summa",
        "ru": "Фиксировано за бронирование",
        "en": "Per booking (fixed)",
    },
}


def sanatorium_meta() -> dict[str, list[Option]]:
    medical = medical_meta()
    stay = stay_meta()
    return {
        "property_types": from_enum(PropertyType, _PROPERTY_TYPE),
        "wellness_categories": from_enum(WellnessCategory, _WELLNESS_CATEGORY),
        "host_types": from_enum(HostType, _HOST_TYPE),
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
        "child_rate_modes": from_labels(_CHILD_RATE_MODE),
        "child_pricing_methods": from_labels(_CHILD_PRICING_METHOD),
        "breakfast_serving_styles": from_labels(_BREAKFAST_SERVING_STYLE),
        "pet_fee_frequencies": from_labels(_PET_FEE_FREQUENCY),
        "deposit_types": from_labels(_DEPOSIT_TYPE),
        "payment_guarantee_methods": from_labels(_PAYMENT_GUARANTEE_METHOD),
        "facility_service_groups": from_labels(_FACILITY_SERVICE_GROUP),
        "tax_pricing_modes": from_labels(_TAX_PRICING_MODE),
        "tax_fee_types": from_labels(_TAX_FEE_TYPE),
        "tax_fee_levels": from_labels(_TAX_FEE_LEVEL),
        "tax_fee_calculation_methods": from_labels(_TAX_FEE_CALCULATION_METHOD),
    }
