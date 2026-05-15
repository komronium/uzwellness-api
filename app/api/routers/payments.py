from fastapi import APIRouter, Depends, Header, Request

from app.api.deps import CurrentUser
from app.schemas.payment import PaymentInitiateRequest, PaymentInitiateResponse
from app.services.payment_service import PaymentService, get_payment_service

router = APIRouter(prefix="/payments", tags=["payments"])


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


@router.post("/payme/webhook")
async def payme_webhook(
    request: Request,
    authorization: str | None = Header(default=None),
    payments: PaymentService = Depends(get_payment_service),
) -> dict:
    body = await request.body()
    payload = await request.json()
    return await payments.handle_payme_webhook(payload, body, authorization)


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
    return await payments.handle_click_webhook(payload)
