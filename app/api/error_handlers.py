"""Last-resort error translation, so no request can answer with a bare 500.

The frontend prints ``detail`` straight to the guest, and anything that
escapes a router would otherwise reach it as Starlette's plain-text
"Internal Server Error" — unreadable, and without CORS headers the browser
hides it behind a CORS failure instead. Everything here turns such a failure
into a JSON body with the same shape as every other error in this API.

Ordering matters: :class:`UnhandledErrorMiddleware` must be registered
*before* CORS in ``main.py`` so that CORS ends up wrapping it and its
responses carry ``Access-Control-Allow-Origin``.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from fastapi import Request, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError

logger = logging.getLogger("uzwellness.errors")

# Postgres SQLSTATE classes we can explain in plain language.
_UNIQUE_VIOLATION = "23505"
_FOREIGN_KEY_VIOLATION = "23503"
_NOT_NULL_VIOLATION = "23502"
_CHECK_VIOLATION = "23514"

_KEY_FIELDS = re.compile(r"Key \(([^)]+)\)=")


def _sqlstate(exc: DBAPIError) -> str | None:
    return getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)


def _pg_error(exc: DBAPIError) -> Any:
    """The asyncpg exception underneath SQLAlchemy's wrapper, when present."""

    return getattr(exc.orig, "__cause__", None)


def _fields(detail: str | None) -> str | None:
    """``Key (room_id, date)=(...) already exists.`` → ``room_id, date``."""

    if not detail:
        return None
    match = _KEY_FIELDS.search(detail)
    return match.group(1) if match else None


def describe_integrity_error(exc: IntegrityError) -> tuple[int, str]:
    """Map a constraint violation to (status code, guest-readable message).

    Only the column names travel to the client — never the offending value,
    which can be a guest's email or phone number, and never the constraint
    name, which means nothing outside the database.
    """

    pg = _pg_error(exc)
    detail = getattr(pg, "detail", None)
    state = _sqlstate(exc)
    fields = _fields(detail)

    if state == _UNIQUE_VIOLATION:
        if fields and "," not in fields:
            return status.HTTP_409_CONFLICT, f"This {fields} is already in use"
        if fields:
            return (
                status.HTTP_409_CONFLICT,
                f"A record with this {fields} already exists",
            )
        return status.HTTP_409_CONFLICT, "This record already exists"

    if state == _FOREIGN_KEY_VIOLATION:
        if detail and "still referenced" in detail:
            return (
                status.HTTP_409_CONFLICT,
                "This record is still used elsewhere and cannot be deleted",
            )
        if fields:
            return (
                status.HTTP_400_BAD_REQUEST,
                f"{fields} refers to a record that does not exist",
            )
        return status.HTTP_400_BAD_REQUEST, "A referenced record does not exist"

    if state == _NOT_NULL_VIOLATION:
        column = getattr(pg, "column_name", None)
        if column:
            return status.HTTP_400_BAD_REQUEST, f"{column} is required"
        return status.HTTP_400_BAD_REQUEST, "A required field is missing"

    if state == _CHECK_VIOLATION:
        return status.HTTP_400_BAD_REQUEST, "The submitted values are not allowed"

    return status.HTTP_409_CONFLICT, "The request conflicts with existing data"


async def integrity_error_handler(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, IntegrityError)
    code, message = describe_integrity_error(exc)
    # The full statement carries parameter values, so it stays in the log.
    logger.warning(
        "%s %s hit a constraint: %s",
        request.method,
        request.url.path,
        getattr(_pg_error(exc), "message", None) or str(exc.orig),
    )
    return JSONResponse(status_code=code, content={"detail": message})


async def database_error_handler(request: Request, exc: Exception) -> Response:
    """A database that is down or dropped the connection is not the caller's fault."""

    logger.error(
        "%s %s could not reach the database: %s",
        request.method,
        request.url.path,
        exc,
    )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Service temporarily unavailable, please retry"},
    )


class UnhandledErrorMiddleware:
    """Answer anything that escapes a router with JSON instead of plain text.

    A reference code goes to both the response and the log, so a guest can
    quote it and the matching traceback is one grep away.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = False

        async def send_wrapper(message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            reference = uuid.uuid4().hex[:12]
            logger.exception(
                "Unhandled error [%s] on %s %s",
                reference,
                scope.get("method"),
                scope.get("path"),
            )
            if started:
                # Headers are already on the wire; nothing left to say.
                raise
            response = JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "detail": (
                        "Something went wrong on our side. "
                        f"Please try again — reference {reference}"
                    )
                },
            )
            await response(scope, receive, send)


def register_error_handlers(app) -> None:
    app.add_exception_handler(IntegrityError, integrity_error_handler)
    app.add_exception_handler(OperationalError, database_error_handler)
