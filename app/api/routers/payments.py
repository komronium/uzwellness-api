import uuid

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser
from app.schemas.payment import PaymentInitiateRequest, PaymentInitiateResponse
from app.services.payment_service import PaymentService, get_payment_service

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post("/initiate", response_model=PaymentInitiateResponse)
async def initiate_payment(
    payload: PaymentInitiateRequest,
    current_user: CurrentUser,
    payments: PaymentService = Depends(get_payment_service),
) -> PaymentInitiateResponse:
    payment = await payments.initiate(
        booking_id=payload.booking_id, method=payload.method, user=current_user
    )
    return PaymentInitiateResponse(payment_id=payment.id, status=payment.status)


@router.post("/{payment_id}/confirm-cash", response_model=PaymentInitiateResponse)
async def confirm_cash_payment(
    payment_id: uuid.UUID,
    current_user: CurrentUser,
    payments: PaymentService = Depends(get_payment_service),
) -> PaymentInitiateResponse:
    payment = await payments.confirm_cash(payment_id, current_user)
    return PaymentInitiateResponse(payment_id=payment.id, status=payment.status)
