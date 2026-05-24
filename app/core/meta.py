"""Selectable option catalogs for admin/front-end dropdowns.

One source of truth for every enum / constrained-value field, each option as
``{value, label: {uz, ru, en}}``. Enum-backed sets derive their values from the
enum itself (so they never drift); free-string sets list a suggested vocabulary.
"""

from enum import StrEnum

from app.models.amenity import AmenityCost
from app.models.booking import BookingStatus, BookingType
from app.models.rate_plan import BoardType, ConfirmationType, PaymentTiming
from app.models.room import RoomView
from app.models.sanatorium import PropertyType, WellnessCategory

type Label = dict[str, str]
type Option = dict[str, str | Label]

_BOARD: dict[str, Label] = {
    "room_only": {"uz": "Faqat yashash", "ru": "Только проживание", "en": "Room only"},
    "breakfast": {"uz": "Nonushta", "ru": "Завтрак", "en": "Breakfast"},
    "half_board": {"uz": "Yarim pansion", "ru": "Полупансион", "en": "Half board"},
    "full_board": {"uz": "To'liq pansion", "ru": "Полный пансион", "en": "Full board"},
    "all_inclusive": {"uz": "Hammasi kiritilgan", "ru": "Всё включено", "en": "All inclusive"},
}
_PAYMENT_TIMING: dict[str, Label] = {
    "prepay": {"uz": "Onlayn to'lov", "ru": "Предоплата онлайн", "en": "Prepay online"},
    "at_hotel": {"uz": "Mehmonxonada to'lov", "ru": "Оплата в отеле", "en": "Pay at hotel"},
    "deposit": {"uz": "Depozit", "ru": "Депозит", "en": "Deposit"},
}
_CONFIRMATION: dict[str, Label] = {
    "instant": {"uz": "Darhol tasdiq", "ru": "Мгновенное подтверждение", "en": "Instant confirmation"},
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
    "landmark": {"uz": "Diqqatga sazovor joy", "ru": "Вид на достопримечательность", "en": "Landmark view"},
}
_AMENITY_COST: dict[str, Label] = {
    "free": {"uz": "Bepul", "ru": "Бесплатно", "en": "Free"},
    "paid": {"uz": "Qo'shimcha to'lov", "ru": "За дополнительную плату", "en": "Additional charge"},
    "on_request": {"uz": "So'rov bo'yicha", "ru": "По запросу", "en": "On request"},
}
_PROPERTY_TYPE: dict[str, Label] = {
    "sanatorium": {"uz": "Sanatoriya", "ru": "Санаторий", "en": "Sanatorium"},
    "wellness": {"uz": "Wellness markaz", "ru": "Велнес-центр", "en": "Wellness center"},
}
_WELLNESS_CATEGORY: dict[str, Label] = {
    "spa_resort": {"uz": "SPA kurort", "ru": "Спа-курорт", "en": "Spa resort"},
    "yoga_retreat": {"uz": "Yoga retrit", "ru": "Йога-ретрит", "en": "Yoga retreat"},
    "meditation_center": {"uz": "Meditatsiya markazi", "ru": "Центр медитации", "en": "Meditation center"},
    "fitness_resort": {"uz": "Fitnes kurort", "ru": "Фитнес-курорт", "en": "Fitness resort"},
    "beauty_spa": {"uz": "Go'zallik SPA", "ru": "Бьюти-спа", "en": "Beauty spa"},
    "digital_detox": {"uz": "Raqamli deteks", "ru": "Цифровой детокс", "en": "Digital detox"},
}
_BOOKING_TYPE: dict[str, Label] = {
    "room": {"uz": "Xona", "ru": "Номер", "en": "Room"},
    "session": {"uz": "Sessiya", "ru": "Сессия", "en": "Session"},
    "package": {"uz": "Paket", "ru": "Пакет", "en": "Package"},
}
_BOOKING_STATUS: dict[str, Label] = {
    "pending": {"uz": "Kutilmoqda", "ru": "В ожидании", "en": "Pending"},
    "confirmed": {"uz": "Tasdiqlangan", "ru": "Подтверждено", "en": "Confirmed"},
    "cancelled": {"uz": "Bekor qilingan", "ru": "Отменено", "en": "Cancelled"},
    "completed": {"uz": "Yakunlangan", "ru": "Завершено", "en": "Completed"},
}

# Free-string fields: not enforced, but a suggested vocabulary for dropdowns.
_BED_TYPE: dict[str, Label] = {
    "single": {"uz": "Bir kishilik", "ru": "Односпальная", "en": "Single bed"},
    "double": {"uz": "Ikki kishilik", "ru": "Двуспальная", "en": "Double bed"},
    "twin": {"uz": "Ikkita alohida", "ru": "Две односпальные", "en": "Twin beds"},
    "queen": {"uz": "Queen", "ru": "Queen", "en": "Queen bed"},
    "king": {"uz": "King", "ru": "King", "en": "King bed"},
    "sofa_bed": {"uz": "Divan-karavot", "ru": "Диван-кровать", "en": "Sofa bed"},
    "bunk": {"uz": "Qavatli karavot", "ru": "Двухъярусная", "en": "Bunk bed"},
}
_TREATMENT_FOCUS: dict[str, Label] = {
    "cardiovascular": {"uz": "Yurak-qon tomir", "ru": "Сердечно-сосудистые", "en": "Cardiovascular"},
    "digestive": {"uz": "Ovqat hazm qilish", "ru": "Пищеварение", "en": "Digestive"},
    "musculoskeletal": {"uz": "Tayanch-harakat", "ru": "Опорно-двигательные", "en": "Musculoskeletal"},
    "respiratory": {"uz": "Nafas olish", "ru": "Дыхательная система", "en": "Respiratory"},
    "neurological": {"uz": "Asab tizimi", "ru": "Неврология", "en": "Neurological"},
    "dermatology": {"uz": "Teri", "ru": "Дерматология", "en": "Dermatology"},
    "endocrine": {"uz": "Endokrin", "ru": "Эндокринная система", "en": "Endocrine"},
    "wellness": {"uz": "Sog'lomlashtirish", "ru": "Велнес", "en": "Wellness"},
}
_PAYMENT_METHOD: dict[str, Label] = {
    "cash": {"uz": "Naqd", "ru": "Наличные", "en": "Cash"},
    "bank_transfer": {"uz": "Bank o'tkazmasi", "ru": "Банковский перевод", "en": "Bank transfer"},
    "uzcard": {"uz": "UzCard", "ru": "UzCard", "en": "UzCard"},
    "visa": {"uz": "Visa", "ru": "Visa", "en": "Visa"},
    "mastercard": {"uz": "Mastercard", "ru": "Mastercard", "en": "Mastercard"},
    "jcb": {"uz": "JCB", "ru": "JCB", "en": "JCB"},
    "unionpay": {"uz": "UnionPay", "ru": "UnionPay", "en": "UnionPay"},
    "mir": {"uz": "Mir", "ru": "Мир", "en": "Mir"},
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
    "food_drink": {"uz": "Ovqat va ichimlik", "ru": "Еда и напитки", "en": "Food & drink"},
    "public_areas": {"uz": "Umumiy hududlar", "ru": "Общие зоны", "en": "Public areas"},
    "children": {"uz": "Bolalar uchun", "ru": "Для детей", "en": "For children"},
    "accessibility": {"uz": "Imkoniyati cheklanganlar", "ru": "Доступность", "en": "Accessibility"},
}
_SURROUNDING_TYPE: dict[str, Label] = {
    "attraction": {"uz": "Diqqatga sazovor joy", "ru": "Достопримечательность", "en": "Attraction"},
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
_TRAVELER_TYPE: dict[str, Label] = {
    "solo": {"uz": "Yakka", "ru": "Один", "en": "Solo"},
    "couple": {"uz": "Juftlik", "ru": "Пара", "en": "Couple"},
    "family": {"uz": "Oila", "ru": "Семья", "en": "Family"},
    "business": {"uz": "Biznes", "ru": "Бизнес", "en": "Business"},
    "friends": {"uz": "Do'stlar", "ru": "Друзья", "en": "Friends"},
}
_CURRENCY: dict[str, Label] = {
    "UZS": {"uz": "So'm", "ru": "Сум", "en": "UZS"},
    "USD": {"uz": "Dollar", "ru": "Доллар", "en": "USD"},
}


def _default_label(value: str) -> Label:
    text = value.replace("_", " ").title()
    return {"uz": text, "ru": text, "en": text}


def _from_labels(labels: dict[str, Label]) -> list[Option]:
    return [{"value": v, "label": label} for v, label in labels.items()]


def _from_enum(enum_cls: type[StrEnum], labels: dict[str, Label]) -> list[Option]:
    # Values come from the enum so the catalog can never drift out of sync;
    # an unlabeled value still appears with a title-cased fallback.
    return [
        {"value": m.value, "label": labels.get(m.value, _default_label(m.value))}
        for m in enum_cls
    ]


META: dict[str, list[Option]] = {
    "board_types": _from_enum(BoardType, _BOARD),
    "payment_timings": _from_enum(PaymentTiming, _PAYMENT_TIMING),
    "confirmation_types": _from_enum(ConfirmationType, _CONFIRMATION),
    "room_views": _from_enum(RoomView, _ROOM_VIEW),
    "amenity_costs": _from_enum(AmenityCost, _AMENITY_COST),
    "property_types": _from_enum(PropertyType, _PROPERTY_TYPE),
    "wellness_categories": _from_enum(WellnessCategory, _WELLNESS_CATEGORY),
    "booking_types": _from_enum(BookingType, _BOOKING_TYPE),
    "booking_statuses": _from_enum(BookingStatus, _BOOKING_STATUS),
    "bed_types": _from_labels(_BED_TYPE),
    "treatment_focuses": _from_labels(_TREATMENT_FOCUS),
    "payment_methods": _from_labels(_PAYMENT_METHOD),
    "amenity_categories": _from_labels(_AMENITY_CATEGORY),
    "surrounding_types": _from_labels(_SURROUNDING_TYPE),
    "venue_types": _from_labels(_VENUE_TYPE),
    "meal_types": _from_labels(_MEAL_TYPE),
    "traveler_types": _from_labels(_TRAVELER_TYPE),
    "currencies": _from_labels(_CURRENCY),
}
