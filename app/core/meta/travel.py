from app.core.currency import supported_display_currencies
from app.core.meta.shared import (
    Label,
    Option,
    default_label,
    from_enum,
    from_labels,
)
from app.models.booking import BookingStatus, BookingType


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

# Currencies the public API can display prices in (?currency= / X-Currency).
# Distinct from `currencies` above, which lists pricing-input currencies
# admins may set on rooms/programs.
_DISPLAY_CURRENCY: dict[str, Label] = {
    "UZS": {"uz": "So'm (UZS)", "ru": "Сум (UZS)", "en": "Uzbek so'm (UZS)"},
    "USD": {
        "uz": "AQSH dollari (USD)",
        "ru": "Доллар США (USD)",
        "en": "US dollar (USD)",
    },
    "EUR": {"uz": "Yevro (EUR)", "ru": "Евро (EUR)", "en": "Euro (EUR)"},
    "RUB": {
        "uz": "Rossiya rubli (RUB)",
        "ru": "Российский рубль (RUB)",
        "en": "Russian ruble (RUB)",
    },
    "KZT": {
        "uz": "Qozog'iston tengesi (KZT)",
        "ru": "Казахстанский тенге (KZT)",
        "en": "Kazakhstani tenge (KZT)",
    },
}


def _display_currencies() -> list[Option]:
    return [
        {"value": code, "label": _DISPLAY_CURRENCY.get(code, default_label(code))}
        for code in supported_display_currencies()
    ]


def travel_meta() -> dict[str, list[Option]]:
    return {
        "booking_types": from_enum(BookingType, _BOOKING_TYPE),
        "booking_statuses": from_enum(BookingStatus, _BOOKING_STATUS),
        "traveler_types": from_labels(_TRAVELER_TYPE),
        "currencies": from_labels(_CURRENCY),
        "display_currencies": _display_currencies(),
    }
