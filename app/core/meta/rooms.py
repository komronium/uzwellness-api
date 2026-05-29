from app.models.rate_plan import BoardType, ConfirmationType, PaymentTiming
from app.models.room import RoomView
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


def room_meta() -> dict[str, list[Option]]:
    return {
        "board_types": from_enum(BoardType, _BOARD),
        "payment_timings": from_enum(PaymentTiming, _PAYMENT_TIMING),
        "confirmation_types": from_enum(ConfirmationType, _CONFIRMATION),
        "room_views": from_enum(RoomView, _ROOM_VIEW),
        "bed_types": from_labels(_BED_TYPE),
    }
