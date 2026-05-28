import json

from fastapi import HTTPException, status


def json_form(value: str | None, *, default):
    if value is None or value == "":
        return default
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON form field",
        ) from exc
    if not isinstance(parsed, type(default)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="JSON form field has invalid type",
        )
    return parsed
