import json

from fastapi import HTTPException, status


def json_form(value: str | None, *, default, field: str):
    """Parse one multipart field that carries JSON.

    Multipart uploads cannot nest, so translations and tag lists arrive as JSON
    strings. When one is malformed the message has to name the field — the
    frontend shows it verbatim, and "Invalid JSON" next to a five-field upload
    form tells the admin nothing about which box to fix.
    """

    if value is None or value == "":
        return default
    shape = "a JSON object" if isinstance(default, dict) else "a JSON array"
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field} is not valid JSON; it must be {shape}",
        ) from exc
    if not isinstance(parsed, type(default)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field} must be {shape}",
        )
    return parsed
