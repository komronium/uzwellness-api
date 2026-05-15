from datetime import date, timedelta


def date_range(start: date, end: date) -> list[date]:
    """Inclusive start, exclusive end — same semantics as check_in/check_out."""
    return [start + timedelta(days=i) for i in range((end - start).days)]


def strip_none(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


def strip_translation_fields(data: dict, fields: tuple[str, ...]) -> None:
    for field in fields:
        if field in data and data[field] is not None:
            data[field] = strip_none(data[field])
