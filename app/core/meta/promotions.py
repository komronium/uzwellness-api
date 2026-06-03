from app.core.meta.shared import Label, Option, from_enum
from app.models.promotion import (
    PromotionAudience,
    PromotionCancellationPolicyMode,
    PromotionCategory,
    PromotionStatus,
)

_PROMOTION_CATEGORY: dict[str, Label] = {
    "mobile_rate": {"uz": "Mobil tarif", "ru": "Мобильный тариф", "en": "Mobile rate"},
    "basic_deal": {"uz": "Asosiy aksiya", "ru": "Базовая акция", "en": "Basic deal"},
    "early_bird": {"uz": "Erta bron", "ru": "Раннее бронирование", "en": "Early bird"},
    "last_minute": {
        "uz": "So'nggi daqiqa",
        "ru": "Последняя минута",
        "en": "Last minute",
    },
    "long_stay": {
        "uz": "Uzoq qolish",
        "ru": "Длительное проживание",
        "en": "Long stay",
    },
    "seasonal": {"uz": "Mavsumiy", "ru": "Сезонная", "en": "Seasonal"},
    "member": {"uz": "A'zolar uchun", "ru": "Для участников", "en": "Member"},
    "package": {"uz": "Paket", "ru": "Пакет", "en": "Package"},
    "custom": {"uz": "Maxsus", "ru": "Индивидуальная", "en": "Custom"},
}

_PROMOTION_STATUS: dict[str, Label] = {
    "active": {"uz": "Faol", "ru": "Активна", "en": "Active"},
    "paused": {"uz": "Pauzada", "ru": "Пауза", "en": "Paused"},
    "inactive": {"uz": "Faol emas", "ru": "Неактивна", "en": "Inactive"},
}

_PROMOTION_AUDIENCE: dict[str, Label] = {
    "all_guests": {"uz": "Barcha mehmonlar", "ru": "Все гости", "en": "All guests"},
}

_PROMOTION_CANCELLATION_POLICY_MODE: dict[str, Label] = {
    "original": {
        "uz": "Asl tarif bilan bir xil",
        "ru": "Как в исходном тарифе",
        "en": "Same as original rate plan",
    },
    "custom": {"uz": "Maxsus", "ru": "Индивидуальная", "en": "Custom"},
}


def promotion_meta() -> dict[str, list[Option]]:
    return {
        "promotion_categories": from_enum(PromotionCategory, _PROMOTION_CATEGORY),
        "promotion_statuses": from_enum(PromotionStatus, _PROMOTION_STATUS),
        "promotion_audiences": from_enum(PromotionAudience, _PROMOTION_AUDIENCE),
        "promotion_cancellation_policy_modes": from_enum(
            PromotionCancellationPolicyMode,
            _PROMOTION_CANCELLATION_POLICY_MODE,
        ),
    }
