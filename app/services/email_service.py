from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger("uzwellness.email")


@dataclass(slots=True)
class BookingEmailContext:
    booking_code: str
    sanatorium_name: str
    check_in: date
    check_out: date
    guest_name: str
    total_price: Decimal
    currency: str


def send_email(*, to: str, subject: str, body: str) -> None:
    if settings.EMAIL_BACKEND == "smtp" and settings.SMTP_HOST:
        _send_smtp(to=to, subject=subject, body=body)
        return
    logger.info("email[%s] → %s: %s\n%s", settings.EMAIL_BACKEND, to, subject, body)


def _send_smtp(*, to: str, subject: str, body: str) -> None:
    if not settings.SMTP_HOST:
        logger.warning("SMTP_HOST not configured; skipping email to %s", to)
        return

    message = EmailMessage()
    message["From"] = settings.EMAIL_FROM
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as client:
            if settings.SMTP_USE_TLS:
                client.starttls()
            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                client.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            client.send_message(message)
    except Exception:
        logger.exception("Failed to send email to %s", to)


def send_booking_received(*, to: str, ctx: BookingEmailContext) -> None:
    send_email(
        to=to,
        subject=f"Booking received — {ctx.booking_code}",
        body=_format_body("Booking received", ctx),
    )


def send_booking_confirmed(*, to: str, ctx: BookingEmailContext) -> None:
    send_email(
        to=to,
        subject=f"Booking confirmed — {ctx.booking_code}",
        body=_format_body("Booking confirmed (payment received)", ctx),
    )


def send_booking_cancelled(*, to: str, ctx: BookingEmailContext) -> None:
    send_email(
        to=to,
        subject=f"Booking cancelled — {ctx.booking_code}",
        body=_format_body("Booking cancelled", ctx),
    )


def _format_body(headline: str, ctx: BookingEmailContext) -> str:
    return (
        f"{headline}\n\n"
        f"Hello {ctx.guest_name},\n\n"
        f"Booking code: {ctx.booking_code}\n"
        f"Sanatorium: {ctx.sanatorium_name}\n"
        f"Check-in: {ctx.check_in.isoformat()}\n"
        f"Check-out: {ctx.check_out.isoformat()}\n"
        f"Total: {ctx.total_price} {ctx.currency}\n\n"
        "— UzWellness"
    )
