"""Uzum Bank Merchant API webhooks plus the guest-facing order lookup.

Uzum posts JSON to ``/payments/uzum/{check,create,confirm,reverse,status}``
with HTTP Basic auth. Every failure — auth, malformed JSON, business rules —
must come back as HTTP 400 with a ``FAILED`` body carrying ``errorCode``, so
these handlers parse and validate the body themselves instead of letting
FastAPI raise its own 401/422.

Spec: https://developer.uzumbank.uz/merchant
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from app.api.deps import CurrentUser
from app.core.config import settings
from app.integrations.uzum import UzumError, UzumErrorCode, verify_basic_auth
from app.models.booking import Booking
from app.models.user import UserRole
from app.schemas.payment import UzumOrderInfo
from app.schemas.uzum import (
    UzumCheckRequest,
    UzumCheckResponse,
    UzumConfirmRequest,
    UzumConfirmResponse,
    UzumCreateRequest,
    UzumCreateResponse,
    UzumErrorResponse,
    UzumReverseRequest,
    UzumReverseResponse,
    UzumStatusRequest,
    UzumStatusResponse,
)
from app.services.uzum_service import (
    UZUM_CURRENCY,
    UzumService,
    get_uzum_service,
    now_ms,
)

logger = logging.getLogger("uzwellness.uzum")

router = APIRouter(prefix="/payments/uzum", tags=["Payments"])

# Time fields each error envelope carries, in the order Uzum's examples show
# them. The first one is stamped with "now"; the rest are explicit nulls.
_ERROR_TIME_FIELDS: dict[str, tuple[str, ...]] = {
    "check": ("timestamp",),
    "create": ("transTime",),
    "confirm": ("confirmTime",),
    "reverse": ("reverseTime",),
    "status": ("transTime", "confirmTime", "reverseTime"),
}

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": UzumErrorResponse, "description": "FAILED with an errorCode"}
}


# --- shared plumbing ---------------------------------------------------------


def _error_response(
    operation: str,
    code: UzumErrorCode,
    *,
    service_id: int | None,
    trans_id: str | None,
) -> JSONResponse:
    body: dict[str, Any] = {"serviceId": service_id}
    if operation != "check":
        body["transId"] = trans_id
    body["status"] = "FAILED"
    for index, field in enumerate(_ERROR_TIME_FIELDS[operation]):
        body[field] = now_ms() if index == 0 else None
    body["errorCode"] = code.value
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=body)


async def _read_payload(request: Request) -> dict:
    raw = await request.body()
    if not raw.strip():
        raise UzumError(UzumErrorCode.JSON_PARSE_ERROR, "Empty request body")
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise UzumError(UzumErrorCode.JSON_PARSE_ERROR, str(exc)) from exc
    if not isinstance(payload, dict):
        raise UzumError(
            UzumErrorCode.JSON_PARSE_ERROR, "Request body must be a JSON object"
        )
    return payload


def _validate[T: BaseModel](model_cls: type[T], payload: dict) -> T:
    try:
        return model_cls.model_validate(payload)
    except ValidationError as exc:
        missing = any(error["type"] == "missing" for error in exc.errors())
        code = (
            UzumErrorCode.MISSING_PARAMETERS
            if missing
            else UzumErrorCode.JSON_PARSE_ERROR
        )
        raise UzumError(code, exc.errors(include_url=False)[0]["msg"]) from exc


async def _run[T: BaseModel](
    request: Request,
    service: UzumService,
    *,
    operation: str,
    model_cls: type[T],
    handler: Callable[[T], Awaitable[BaseModel]],
) -> JSONResponse:
    service_id: int | None = None
    trans_id: str | None = None
    try:
        verify_basic_auth(request.headers)
        payload = await _read_payload(request)
        service_id = _as_int(payload.get("serviceId"))
        trans_id = _as_str(payload.get("transId"))
        result = await handler(_validate(model_cls, payload))
    except UzumError as exc:
        logger.warning("Uzum /%s rejected: %s", operation, exc)
        await service.db.rollback()
        return _error_response(
            operation, exc.code, service_id=service_id, trans_id=trans_id
        )
    except Exception:
        logger.exception("Uzum /%s failed unexpectedly", operation)
        await service.db.rollback()
        return _error_response(
            operation,
            UzumErrorCode.INTERNAL_ERROR,
            service_id=service_id,
            trans_id=trans_id,
        )
    return JSONResponse(content=result.model_dump(by_alias=True))


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_str(value: Any) -> str | None:
    return None if value is None else str(value)


# --- webhooks ----------------------------------------------------------------


@router.post(
    "/check",
    summary="Uzum webhook: verify payment possibility",
    responses={200: {"model": UzumCheckResponse}, **_ERROR_RESPONSES},
)
async def uzum_check(
    request: Request,
    service: UzumService = Depends(get_uzum_service),
) -> JSONResponse:
    return await _run(
        request,
        service,
        operation="check",
        model_cls=UzumCheckRequest,
        handler=service.check,
    )


@router.post(
    "/create",
    summary="Uzum webhook: create payment transaction",
    responses={200: {"model": UzumCreateResponse}, **_ERROR_RESPONSES},
)
async def uzum_create(
    request: Request,
    service: UzumService = Depends(get_uzum_service),
) -> JSONResponse:
    return await _run(
        request,
        service,
        operation="create",
        model_cls=UzumCreateRequest,
        handler=service.create,
    )


@router.post(
    "/confirm",
    summary="Uzum webhook: confirm payment transaction",
    responses={200: {"model": UzumConfirmResponse}, **_ERROR_RESPONSES},
)
async def uzum_confirm(
    request: Request,
    service: UzumService = Depends(get_uzum_service),
) -> JSONResponse:
    return await _run(
        request,
        service,
        operation="confirm",
        model_cls=UzumConfirmRequest,
        handler=service.confirm,
    )


@router.post(
    "/reverse",
    summary="Uzum webhook: cancel payment transaction",
    responses={200: {"model": UzumReverseResponse}, **_ERROR_RESPONSES},
)
async def uzum_reverse(
    request: Request,
    service: UzumService = Depends(get_uzum_service),
) -> JSONResponse:
    return await _run(
        request,
        service,
        operation="reverse",
        model_cls=UzumReverseRequest,
        handler=service.reverse,
    )


@router.post(
    "/status",
    summary="Uzum webhook: read payment transaction status",
    responses={200: {"model": UzumStatusResponse}, **_ERROR_RESPONSES},
)
async def uzum_status(
    request: Request,
    service: UzumService = Depends(get_uzum_service),
) -> JSONResponse:
    return await _run(
        request,
        service,
        operation="status",
        model_cls=UzumStatusRequest,
        handler=service.status,
    )


# Uzum expects errorCode 10003 — not an HTML 405 — when a webhook is called
# with the wrong verb.
@router.api_route(
    "/{operation}",
    methods=["GET", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
async def uzum_invalid_operation(operation: str) -> JSONResponse:
    if operation not in _ERROR_TIME_FIELDS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return _error_response(
        operation,
        UzumErrorCode.INVALID_OPERATION,
        service_id=None,
        trans_id=None,
    )


# --- guest-facing helper -----------------------------------------------------


@router.get(
    "/order/{booking_id}",
    response_model=UzumOrderInfo,
    summary="What the guest must type into the Uzum Bank app",
)
async def uzum_order_info(
    booking_id: uuid.UUID,
    current_user: CurrentUser,
    service: UzumService = Depends(get_uzum_service),
) -> UzumOrderInfo:
    booking = await service.db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found"
        )
    if current_user.role == UserRole.CUSTOMER and booking.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to view this booking",
        )
    try:
        amount = await service.expected_amount_uzs(booking)
    except UzumError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=exc.detail
        ) from exc
    return UzumOrderInfo(
        booking_id=booking.id,
        order_id=booking.reservation_number,
        service_id=settings.UZUM_SERVICE_ID,
        amount=amount,
        currency=UZUM_CURRENCY,
    )
