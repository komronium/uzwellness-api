from app.models.review import ReviewAppealStatus, ReviewReplyStatus, ReviewSource

from app.core.meta.shared import Label, Option, from_enum, from_labels

_REVIEW_SOURCE: dict[str, Label] = {
    "uzwellness": {"uz": "UzWellness", "ru": "UzWellness", "en": "UzWellness"},
    "trip_com": {"uz": "Trip.com", "ru": "Trip.com", "en": "Trip.com"},
    "qunar": {"uz": "Qunar", "ru": "Qunar", "en": "Qunar"},
    "ly_com": {"uz": "Ly.com", "ru": "Ly.com", "en": "Ly.com"},
    "google": {"uz": "Google", "ru": "Google", "en": "Google"},
    "booking_com": {"uz": "Booking.com", "ru": "Booking.com", "en": "Booking.com"},
}

_REVIEW_REPLY_STATUS: dict[str, Label] = {
    "awaiting_reply": {
        "uz": "Javob kutilmoqda",
        "ru": "Ожидает ответа",
        "en": "Awaiting reply",
    },
    "replied": {"uz": "Javob berilgan", "ru": "Отвечено", "en": "Replied"},
    "not_required": {"uz": "Shart emas", "ru": "Не требуется", "en": "Not required"},
}

_REVIEW_APPEAL_STATUS: dict[str, Label] = {
    "none": {"uz": "Yo'q", "ru": "Нет", "en": "None"},
    "submitted": {"uz": "Yuborilgan", "ru": "Отправлено", "en": "Submitted"},
    "approved": {"uz": "Qabul qilingan", "ru": "Принято", "en": "Approved"},
    "rejected": {"uz": "Rad etilgan", "ru": "Отклонено", "en": "Rejected"},
}

_REVIEW_SORT: dict[str, Label] = {
    "-created_at": {"uz": "Eng yangi", "ru": "Сначала новые", "en": "Newest first"},
    "created_at": {"uz": "Eng eski", "ru": "Сначала старые", "en": "Oldest first"},
    "-rating": {"uz": "Yuqori baho", "ru": "Высокая оценка", "en": "Highest rating"},
    "rating": {"uz": "Past baho", "ru": "Низкая оценка", "en": "Lowest rating"},
}


def review_meta() -> dict[str, list[Option]]:
    return {
        "review_sources": from_enum(ReviewSource, _REVIEW_SOURCE),
        "review_reply_statuses": from_enum(ReviewReplyStatus, _REVIEW_REPLY_STATUS),
        "review_appeal_statuses": from_enum(ReviewAppealStatus, _REVIEW_APPEAL_STATUS),
        "review_sort_options": from_labels(_REVIEW_SORT),
    }
