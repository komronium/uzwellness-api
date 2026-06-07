from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TASHKENT_TZ = ZoneInfo("Asia/Tashkent")


def today_tashkent() -> date:
    """Return today's date in Asia/Tashkent — for booking check_in cutoffs."""
    return datetime.now(TASHKENT_TZ).date()


def date_range(start: date, end: date) -> list[date]:
    """Inclusive start, exclusive end — same semantics as check_in/check_out."""
    return [start + timedelta(days=i) for i in range((end - start).days)]


def pick_locale(translations: dict | None, locale: str = "uz") -> str:
    """Pick a display string from a translations dict.

    Tries the requested locale, then falls through uz → ru → en, then any
    non-empty value. Returns an empty string if the dict has nothing usable.
    """
    if not translations:
        return ""
    preferred = translations.get(locale)
    if preferred:
        return preferred
    for k in ("uz", "ru", "en"):
        value = translations.get(k)
        if value:
            return value
    for value in translations.values():
        if value:
            return value
    return ""


def merge_translation_fields(obj, data: dict, fields: tuple[str, ...]) -> None:
    """Merge partial Translations payloads into the existing JSONB dict on `obj`.

    For each named field present in `data`:
      - if the payload value is None, drop it from `data` (no-op);
      - otherwise overlay the partial dict on top of `getattr(obj, field)` and
        drop None values, so existing translations the client did not send are
        preserved.
    """
    for field in fields:
        if field not in data:
            continue
        partial = data[field]
        if partial is None:
            data.pop(field)
            continue
        current = getattr(obj, field) or {}
        merged = {**current, **partial}
        data[field] = {k: v for k, v in merged.items() if v is not None}
