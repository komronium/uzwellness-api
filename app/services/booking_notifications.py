"""Best-effort customer notifications for a freshly created booking.

Sends a confirmation email with the booking voucher attached as a PDF. Failures
never break the booking request — they are logged and swallowed, and the booking
itself is already committed by the time this runs.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.sanatorium_lookup import sanatorium_name_for_booking
from app.models.booking import Booking
from app.models.notification import Notification
from app.models.user import User
from app.services.booking_voucher import build_voucher_pdf
from app.services.email_service import EmailAttachment, send_email

logger = logging.getLogger("uzwellness.bookings")

_SUBJECT: dict[str, str] = {
    "en": "Booking confirmation — {code}",
    "ru": "Подтверждение бронирования — {code}",
    "uz": "Bron tasdiqlandi — {code}",
}

_BODY: dict[str, str] = {
    "en": (
        "Hello{name},\n\n"
        "Thank you for your booking. Here are the details:\n\n"
        "Confirmation number: {reservation_number}\n"
        "Booking code: {code}\n"
        "Property: {sanatorium}\n"
        "Check-in: {check_in}\n"
        "Check-out: {check_out}\n"
        "Guests: {guests}\n"
        "Total: {total} {currency}\n\n"
        "Your booking voucher is attached as a PDF.\n\n"
        "— UzWellness"
    ),
    "ru": (
        "Здравствуйте{name}!\n\n"
        "Благодарим за бронирование. Детали:\n\n"
        "Номер подтверждения: {reservation_number}\n"
        "Код бронирования: {code}\n"
        "Объект размещения: {sanatorium}\n"
        "Заезд: {check_in}\n"
        "Отъезд: {check_out}\n"
        "Гостей: {guests}\n"
        "Итого: {total} {currency}\n\n"
        "Ваш ваучер прикреплён в формате PDF.\n\n"
        "— UzWellness"
    ),
    "uz": (
        "Assalomu alaykum{name}!\n\n"
        "Bron uchun rahmat. Tafsilotlar:\n\n"
        "Tasdiqlash raqami: {reservation_number}\n"
        "Bron kodi: {code}\n"
        "Obyekt: {sanatorium}\n"
        "Kelish: {check_in}\n"
        "Ketish: {check_out}\n"
        "Mehmonlar: {guests}\n"
        "Jami: {total} {currency}\n\n"
        "Bron vaucheringiz PDF shaklida ilova qilingan.\n\n"
        "— UzWellness"
    ),
}


async def send_booking_confirmation_email(
    db: AsyncSession, booking: Booking, locale: str = "en"
) -> None:
    """Email the customer their confirmation with the voucher PDF attached."""
    user = await db.get(User, booking.user_id) if booking.user_id else None
    if user is None or not user.email:
        return

    lang = locale if locale in _BODY else "en"
    try:
        pdf = await build_voucher_pdf(db, booking, lang)
        sanatorium_name = await sanatorium_name_for_booking(db, booking) or ""
        greeting = f" {user.full_name}" if user.full_name else ""
        body = _BODY[lang].format(
            name=greeting,
            reservation_number=booking.reservation_number,
            code=booking.code,
            sanatorium=sanatorium_name,
            check_in=booking.check_in.isoformat(),
            check_out=booking.check_out.isoformat(),
            guests=booking.guests,
            total=booking.final_price,
            currency=booking.currency,
        )
        send_email(
            to=user.email,
            subject=_SUBJECT[lang].format(code=booking.code),
            body=body,
            attachments=[
                EmailAttachment(
                    filename=f"Booking #{booking.reservation_number}.pdf",
                    content=pdf,
                    maintype="application",
                    subtype="pdf",
                )
            ],
        )
        db.add(
            Notification(
                booking_id=booking.id,
                type="booking_confirmation",
                channel="email",
            )
        )
        await db.commit()
    except Exception:
        logger.exception("Failed to send booking confirmation for %s", booking.id)
        await db.rollback()
