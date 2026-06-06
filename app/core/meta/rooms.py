from app.models.rate_plan import BoardType, ConfirmationType, PaymentTiming
from app.models.room import (
    AccommodationType,
    GenderRestriction,
    RoomSizePolicy,
    RoomView,
    SmokingPolicy,
    WindowPolicy,
)
from app.models.stay_option import StayOptionGuestType
from app.core.meta.shared import Label, Option, from_enum, from_labels


_BOARD: dict[str, Label] = {
    "room_only": {"uz": "Faqat yashash", "ru": "Только проживание", "en": "Room only"},
    "breakfast": {"uz": "Nonushta", "ru": "Завтрак", "en": "Breakfast"},
    "half_board": {"uz": "Yarim pansion", "ru": "Полупансион", "en": "Half board"},
    "full_board": {"uz": "To'liq pansion", "ru": "Полный пансион", "en": "Full board"},
    "all_inclusive": {
        "uz": "Hammasi kiritilgan",
        "ru": "Всё включено",
        "en": "All inclusive",
    },
}

_ROOM_OFFER_PACKAGE_KIND: dict[str, Label] = {
    "treatment": {
        "uz": "Davolash paketi",
        "ru": "Лечебный пакет",
        "en": "Treatment package",
    },
    "special": {
        "uz": "Maxsus paket",
        "ru": "Специальный пакет",
        "en": "Special package",
    },
}

_STAY_OPTION_GUEST_TYPE: dict[str, Label] = {
    "adult": {"uz": "Katta", "ru": "Взрослый", "en": "Adult"},
    "child": {"uz": "Bola", "ru": "Ребенок", "en": "Child"},
}

_ROOM_GUEST_OPTION_PRESET: dict[str, Label] = {
    "full_board_and_treatment": {
        "uz": "To'liq pansion va davolash",
        "ru": "Полный пансион и лечение",
        "en": "Full board and treatment",
    },
    "half_board_and_treatment": {
        "uz": "Yarim pansion va davolash",
        "ru": "Полупансион и лечение",
        "en": "Half board and treatment",
    },
    "full_board_without_treatment": {
        "uz": "To'liq pansion, davolashsiz",
        "ru": "Полный пансион без лечения",
        "en": "Full board without treatment",
    },
    "half_board_without_treatment": {
        "uz": "Yarim pansion, davolashsiz",
        "ru": "Полупансион без лечения",
        "en": "Half board without treatment",
    },
}

_PAYMENT_TIMING: dict[str, Label] = {
    "prepay": {"uz": "Onlayn to'lov", "ru": "Предоплата онлайн", "en": "Prepay online"},
    "at_hotel": {
        "uz": "Mehmonxonada to'lov",
        "ru": "Оплата в отеле",
        "en": "Pay at hotel",
    },
    "deposit": {"uz": "Depozit", "ru": "Депозит", "en": "Deposit"},
}

_CONFIRMATION: dict[str, Label] = {
    "instant": {
        "uz": "Darhol tasdiq",
        "ru": "Мгновенное подтверждение",
        "en": "Instant confirmation",
    },
    "on_request": {"uz": "So'rov bo'yicha", "ru": "По запросу", "en": "On request"},
}

_ROOM_VIEW: dict[str, Label] = {
    "city": {"uz": "Shahar manzarasi", "ru": "Вид на город", "en": "City view"},
    "sea": {"uz": "Dengiz manzarasi", "ru": "Вид на море", "en": "Sea view"},
    "garden": {"uz": "Bog' manzarasi", "ru": "Вид на сад", "en": "Garden view"},
    "mountain": {"uz": "Tog' manzarasi", "ru": "Вид на горы", "en": "Mountain view"},
    "pool": {"uz": "Basseyn manzarasi", "ru": "Вид на бассейн", "en": "Pool view"},
    "lake": {"uz": "Ko'l manzarasi", "ru": "Вид на озеро", "en": "Lake view"},
    "park": {"uz": "Park manzarasi", "ru": "Вид на парк", "en": "Park view"},
    "courtyard": {"uz": "Hovli manzarasi", "ru": "Вид во двор", "en": "Courtyard view"},
    "street": {"uz": "Ko'cha manzarasi", "ru": "Вид на улицу", "en": "Street view"},
    "landmark": {
        "uz": "Diqqatga sazovor joy",
        "ru": "Вид на достопримечательность",
        "en": "Landmark view",
    },
}

_BED_TYPE: dict[str, Label] = {
    "single": {"uz": "Bir kishilik", "ru": "Односпальная", "en": "Single bed"},
    "double": {"uz": "Ikki kishilik", "ru": "Двуспальная", "en": "Double bed"},
    "twin": {"uz": "Ikkita alohida", "ru": "Две односпальные", "en": "Twin beds"},
    "queen": {"uz": "Queen", "ru": "Queen", "en": "Queen bed"},
    "king": {"uz": "King", "ru": "King", "en": "King bed"},
    "sofa_bed": {"uz": "Divan-karavot", "ru": "Диван-кровать", "en": "Sofa bed"},
    "bunk": {"uz": "Qavatli karavot", "ru": "Двухъярусная", "en": "Bunk bed"},
}

_ACCOMMODATION_TYPE: dict[str, Label] = {
    "hotel_room": {"uz": "Mehmonxona xonasi", "ru": "Номер", "en": "Hotel room"},
    "shared_room_bed": {
        "uz": "Umumiy xonadagi karavot",
        "ru": "Кровать в общем номере",
        "en": "Bed in shared room",
    },
}

_GENDER_RESTRICTION: dict[str, Label] = {
    "male_only": {"uz": "Faqat erkaklar", "ru": "Только мужчины", "en": "Male only"},
    "female_only": {
        "uz": "Faqat ayollar",
        "ru": "Только женщины",
        "en": "Female only",
    },
}

_ROOM_SIZE_POLICY: dict[str, Label] = {
    "same_size": {
        "uz": "Barcha xonalar bir xil o'lchamda",
        "ru": "Все номера одного размера",
        "en": "All rooms have the same size",
    },
    "different_sizes": {
        "uz": "Xonalar har xil o'lchamda",
        "ru": "Номера разного размера",
        "en": "Rooms have different sizes",
    },
}

_SMOKING_POLICY: dict[str, Label] = {
    "non_smoking": {"uz": "Chekilmaydi", "ru": "Для некурящих", "en": "Non-smoking"},
    "smoking_permitted": {
        "uz": "Chekish mumkin",
        "ru": "Курение разрешено",
        "en": "Smoking permitted",
    },
    "some_smoking": {
        "uz": "Ba'zi xonalarda chekish mumkin",
        "ru": "Курение разрешено в некоторых номерах",
        "en": "Smoking permitted in some rooms",
    },
}

_WINDOW_POLICY: dict[str, Label] = {
    "all_rooms_have_windows": {
        "uz": "Barcha xonalarda deraza bor",
        "ru": "Во всех номерах есть окна",
        "en": "All rooms have windows",
    },
    "some_rooms_have_windows": {
        "uz": "Ba'zi xonalarda deraza bor",
        "ru": "В некоторых номерах есть окна",
        "en": "Some rooms have windows",
    },
    "no_rooms_have_windows": {
        "uz": "Xonalarda deraza yo'q",
        "ru": "В номерах нет окон",
        "en": "No rooms have windows",
    },
}

_ROOM_AMENITY_GROUP: dict[str, Label] = {
    "popular_amenities": {
        "uz": "Mashhur qulayliklar",
        "ru": "Популярные удобства",
        "en": "Popular amenities",
    },
    "bathroom": {"uz": "Hammom", "ru": "Ванная", "en": "Bathroom"},
    "bedroom": {"uz": "Yotoqxona", "ru": "Спальня", "en": "Bedroom"},
    "media_technology": {
        "uz": "Media va texnologiya",
        "ru": "Медиа и технологии",
        "en": "Media and technology",
    },
    "internet": {"uz": "Internet", "ru": "Интернет", "en": "Internet"},
    "kitchen": {"uz": "Oshxona", "ru": "Кухня", "en": "Kitchen"},
    "food_drink": {
        "uz": "Ovqat va ichimlik",
        "ru": "Еда и напитки",
        "en": "Food and drink",
    },
    "comfort": {"uz": "Qulaylik", "ru": "Комфорт", "en": "Comfort"},
    "heating_cooling": {
        "uz": "Isitish va sovitish",
        "ru": "Отопление и охлаждение",
        "en": "Heating and cooling",
    },
    "layout_furnishing": {
        "uz": "Joylashuv va mebel",
        "ru": "Планировка и мебель",
        "en": "Layout and furnishing",
    },
    "safety_security": {
        "uz": "Xavfsizlik",
        "ru": "Безопасность",
        "en": "Safety and security",
    },
    "outdoor_view": {"uz": "Tashqi ko'rinish", "ru": "Вид", "en": "Outdoor and view"},
    "services": {"uz": "Xizmatlar", "ru": "Услуги", "en": "Services"},
    "family": {"uz": "Oila", "ru": "Семья", "en": "Family"},
    "accessibility": {
        "uz": "Maxsus imkoniyatlar",
        "ru": "Доступность",
        "en": "Accessibility",
    },
}


def room_meta() -> dict[str, list[Option]]:
    return {
        "board_types": from_enum(BoardType, _BOARD),
        "stay_option_guest_types": from_enum(
            StayOptionGuestType, _STAY_OPTION_GUEST_TYPE
        ),
        "room_offer_package_kinds": from_labels(_ROOM_OFFER_PACKAGE_KIND),
        "room_guest_option_presets": from_labels(_ROOM_GUEST_OPTION_PRESET),
        "payment_timings": from_enum(PaymentTiming, _PAYMENT_TIMING),
        "confirmation_types": from_enum(ConfirmationType, _CONFIRMATION),
        "room_views": from_enum(RoomView, _ROOM_VIEW),
        "bed_types": from_labels(_BED_TYPE),
        "accommodation_types": from_enum(AccommodationType, _ACCOMMODATION_TYPE),
        "gender_restrictions": from_enum(GenderRestriction, _GENDER_RESTRICTION),
        "room_size_policies": from_enum(RoomSizePolicy, _ROOM_SIZE_POLICY),
        "smoking_policies": from_enum(SmokingPolicy, _SMOKING_POLICY),
        "window_policies": from_enum(WindowPolicy, _WINDOW_POLICY),
        "room_amenity_groups": from_labels(_ROOM_AMENITY_GROUP),
    }
