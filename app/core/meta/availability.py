from app.core.meta.shared import Label, Option, from_enum, from_labels
from app.models.availability_log import AvailabilityLogCategory
from app.schemas.booking import BookingDateFilter
from app.schemas.bulk_availability import (
    CopyRateAdjustment,
    CopyRateAlignment,
    RestrictionField,
)
from app.schemas.sanatorium_reservation import ReservationFallbackProcessingMethod


_BOOKING_DATE_FILTER: dict[str, Label] = {
    "booking_date": {
        "uz": "Bron sanasi",
        "ru": "Дата бронирования",
        "en": "Booking date",
    },
    "check_in": {"uz": "Kirish sanasi", "ru": "Дата заезда", "en": "Check-in"},
    "check_out": {"uz": "Chiqish sanasi", "ru": "Дата выезда", "en": "Check-out"},
}

_WEEKDAY: dict[str, Label] = {
    "0": {"uz": "Dushanba", "ru": "Понедельник", "en": "Monday"},
    "1": {"uz": "Seshanba", "ru": "Вторник", "en": "Tuesday"},
    "2": {"uz": "Chorshanba", "ru": "Среда", "en": "Wednesday"},
    "3": {"uz": "Payshanba", "ru": "Четверг", "en": "Thursday"},
    "4": {"uz": "Juma", "ru": "Пятница", "en": "Friday"},
    "5": {"uz": "Shanba", "ru": "Суббота", "en": "Saturday"},
    "6": {"uz": "Yakshanba", "ru": "Воскресенье", "en": "Sunday"},
}

_BULK_RESTRICTION_FIELD: dict[str, Label] = {
    "min_advance_hours": {
        "uz": "Minimal oldindan bron",
        "ru": "Мин. предварительное бронирование",
        "en": "Min. advance reservation",
    },
    "max_advance_hours": {
        "uz": "Maksimal oldindan bron",
        "ru": "Макс. предварительное бронирование",
        "en": "Max. advance reservation",
    },
    "min_stay_nights": {
        "uz": "Minimal tunlar soni",
        "ru": "Мин. длительность проживания",
        "en": "Min. length of stay",
    },
    "min_stay_arrival_nights": {
        "uz": "Kirish sanasidan minimal tunlar",
        "ru": "Мин. проживание с даты заезда",
        "en": "Min. length of stay from arrival",
    },
}

_COPY_RATE_ALIGNMENT: dict[str, Label] = {
    "day_of_week": {
        "uz": "Hafta kuni bo'yicha",
        "ru": "По дню недели",
        "en": "Align by day of week",
    },
    "date_order": {
        "uz": "Sana tartibi bo'yicha",
        "ru": "По порядку дат",
        "en": "Align by date order",
    },
    "custom_range": {
        "uz": "Maxsus davr bo'yicha",
        "ru": "По произвольному периоду",
        "en": "Align by custom range",
    },
}

_COPY_RATE_ADJUSTMENT: dict[str, Label] = {
    "none": {"uz": "O'zgarishsiz", "ru": "Без изменений", "en": "No adjustment"},
    "increase_percent": {
        "uz": "Foizga oshirish",
        "ru": "Увеличить на процент",
        "en": "Increase by percent",
    },
    "decrease_percent": {
        "uz": "Foizga kamaytirish",
        "ru": "Уменьшить на процент",
        "en": "Decrease by percent",
    },
}

_RESERVATION_FALLBACK_PROCESSING_METHOD: dict[str, Label] = {
    "email": {"uz": "Email", "ru": "Email", "en": "Email"},
    "phone": {"uz": "Telefon", "ru": "Телефон", "en": "Phone"},
    "sms": {"uz": "SMS", "ru": "SMS", "en": "SMS"},
}

_AVAILABILITY_ROOM_STATUS: dict[str, Label] = {
    "bookable": {"uz": "Bron qilish mumkin", "ru": "Доступно", "en": "Bookable"},
    "unbookable": {
        "uz": "Bron qilish mumkin emas",
        "ru": "Недоступно",
        "en": "Unbookable",
    },
}

_AVAILABILITY_LOG_CATEGORY: dict[str, Label] = {
    "room_status_restrictions": {
        "uz": "Xona holati va cheklovlar",
        "ru": "Статус номера и ограничения",
        "en": "Room status & restrictions",
    },
    "inventory": {"uz": "Inventar", "ru": "Инвентарь", "en": "Inventory"},
    "rate": {"uz": "Narx", "ru": "Тариф", "en": "Rate"},
    "max_rooms_available": {
        "uz": "Maksimal mavjud xonalar",
        "ru": "Максимум доступных номеров",
        "en": "Maximum rooms available",
    },
    "cancellation_policy": {
        "uz": "Bekor qilish siyosati",
        "ru": "Политика отмены",
        "en": "Cancellation policy",
    },
    "bulk_operation": {
        "uz": "Ommaviy operatsiya",
        "ru": "Массовая операция",
        "en": "Bulk operation",
    },
}


def availability_meta() -> dict[str, list[Option]]:
    return {
        "booking_date_filters": from_enum(BookingDateFilter, _BOOKING_DATE_FILTER),
        "weekdays": from_labels(_WEEKDAY),
        "weekend_days": [
            item for item in from_labels(_WEEKDAY) if item["value"] in {"4", "5"}
        ],
        "bulk_restriction_fields": from_enum(
            RestrictionField,
            _BULK_RESTRICTION_FIELD,
        ),
        "copy_rate_alignments": from_enum(CopyRateAlignment, _COPY_RATE_ALIGNMENT),
        "copy_rate_adjustments": from_enum(CopyRateAdjustment, _COPY_RATE_ADJUSTMENT),
        "reservation_fallback_processing_methods": from_enum(
            ReservationFallbackProcessingMethod,
            _RESERVATION_FALLBACK_PROCESSING_METHOD,
        ),
        "availability_room_statuses": from_labels(_AVAILABILITY_ROOM_STATUS),
        "availability_log_categories": from_enum(
            AvailabilityLogCategory,
            _AVAILABILITY_LOG_CATEGORY,
        ),
    }
