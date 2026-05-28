import uuid

from fastapi import APIRouter, Depends, Request

from app.api.deps import CurrentUser
from app.models.payment import PaymentMethod
from app.schemas.payment import PaymentInitiateRequest, PaymentInitiateResponse
from app.services.payment_service import PaymentService, get_payment_service

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post("/initiate", response_model=PaymentInitiateResponse)
async def initiate_payment(
    payload: PaymentInitiateRequest,
    current_user: CurrentUser,
    payments: PaymentService = Depends(get_payment_service),
) -> PaymentInitiateResponse:
    payment, redirect_url = await payments.initiate(
        booking_id=payload.booking_id, method=payload.method, user=current_user
    )
    return PaymentInitiateResponse(
        payment_id=payment.id,
        status=payment.status,
        redirect_url=redirect_url,
    )


@router.post("/{payment_id}/confirm-cash", response_model=PaymentInitiateResponse)
async def confirm_cash_payment(
    payment_id: uuid.UUID,
    current_user: CurrentUser,
    payments: PaymentService = Depends(get_payment_service),
) -> PaymentInitiateResponse:
    payment = await payments.confirm_cash(payment_id, current_user)
    return PaymentInitiateResponse(
        payment_id=payment.id,
        status=payment.status,
        redirect_url=None,
    )


@router.post("/payme/webhook")
async def payme_webhook(
    request: Request,
    payments: PaymentService = Depends(get_payment_service),
) -> dict:
    payload = await request.json()
    return await payments.handle_webhook(
        PaymentMethod.PAYME,
        payload=payload,
        headers=request.headers,
    )


@router.post("/click/webhook")
async def click_webhook(
    request: Request,
    payments: PaymentService = Depends(get_payment_service),
) -> dict:
    if request.headers.get("content-type", "").startswith("application/json"):
        payload = await request.json()
    else:
        form = await request.form()
        payload = {k: v for k, v in form.items()}
    return await payments.handle_webhook(
        PaymentMethod.CLICK,
        payload=payload,
        headers=request.headers,
    )
