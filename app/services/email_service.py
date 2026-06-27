from __future__ import annotations

import base64
import logging
import smtplib
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from email.message import EmailMessage

import httpx

from app.core.config import settings

logger = logging.getLogger("uzwellness.email")

# SMTP is blocking; send off the event loop. Failures are logged, not raised
# (same at-most-once guarantee as before).
_smtp_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="smtp")


@dataclass(slots=True)
class EmailAttachment:
    filename: str
    content: bytes
    maintype: str = "application"
    subtype: str = "octet-stream"


@dataclass(slots=True)
class BookingEmailContext:
    booking_code: str
    sanatorium_name: str
    check_in: date
    check_out: date
    guest_name: str
    total_price: Decimal
    currency: str


def send_email(
    *,
    to: str,
    subject: str,
    body: str,
    attachments: Sequence[EmailAttachment] | None = None,
) -> None:
    if settings.EMAIL_BACKEND == "smtp" and settings.SMTP_HOST:
        _smtp_executor.submit(
            _send_smtp, to=to, subject=subject, body=body, attachments=attachments
        )
        return
    if settings.EMAIL_BACKEND == "resend" and settings.RESEND_API_KEY:
        _smtp_executor.submit(
            _send_resend, to=to, subject=subject, body=body, attachments=attachments
        )
        return
    extra = f" (+{len(attachments)} attachment(s))" if attachments else ""
    logger.info(
        "email[%s] → %s: %s%s\n%s", settings.EMAIL_BACKEND, to, subject, extra, body
    )


def _send_resend(
    *,
    to: str,
    subject: str,
    body: str,
    attachments: Sequence[EmailAttachment] | None = None,
) -> None:
    """Send via the Resend HTTPS API (port 443) — works where SMTP is blocked."""
    if not settings.RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not configured; skipping email to %s", to)
        return

    payload: dict = {
        "from": settings.EMAIL_FROM,
        "to": [to],
        "subject": subject,
        "text": body,
    }
    if attachments:
        payload["attachments"] = [
            {
                "filename": a.filename,
                "content": base64.b64encode(a.content).decode("ascii"),
            }
            for a in attachments
        ]

    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
            json=payload,
            timeout=15,
        )
        response.raise_for_status()
    except Exception:
        logger.exception("Failed to send email via Resend to %s", to)


def _send_smtp(
    *,
    to: str,
    subject: str,
    body: str,
    attachments: Sequence[EmailAttachment] | None = None,
) -> None:
    if not settings.SMTP_HOST:
        logger.warning("SMTP_HOST not configured; skipping email to %s", to)
        return

    message = EmailMessage()
    message["From"] = settings.EMAIL_FROM
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    for attachment in attachments or ():
        message.add_attachment(
            attachment.content,
            maintype=attachment.maintype,
            subtype=attachment.subtype,
            filename=attachment.filename,
        )

    try:
        with _smtp_client() as client:
            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                client.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            client.send_message(message)
    except Exception:
        logger.exception("Failed to send email to %s", to)


def _smtp_client() -> smtplib.SMTP:
    """Open an SMTP connection: implicit SSL (465) or STARTTLS (587)."""
    if settings.SMTP_USE_SSL:
        return smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT)
    client = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
    if settings.SMTP_USE_TLS:
        client.starttls()
    return client


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


def send_cancellation_code(
    *, to: str, code: str, booking_code: str, minutes: int
) -> None:
    send_email(
        to=to,
        subject=f"Cancellation code — {booking_code}",
        body=(
            "You requested to cancel your booking.\n\n"
            f"Booking code: {booking_code}\n"
            f"Your cancellation code: {code}\n"
            f"This code expires in {minutes} minutes.\n\n"
            "Enter it to submit your cancellation request. The property will then "
            "review and process the refund.\n\n"
            "If you did not request this, you can ignore this email.\n\n"
            "— UzWellness"
        ),
    )


def send_admin_cancellation_request(
    *, to: str, booking_code: str, reservation_number: str
) -> None:
    send_email(
        to=to,
        subject=f"Cancellation request — {booking_code}",
        body=(
            "A guest has requested to cancel a booking and confirmed it by email.\n\n"
            f"Booking code: {booking_code}\n"
            f"Confirmation number: {reservation_number}\n\n"
            "Please review and approve or reject the cancellation in the admin "
            "panel. Approving will cancel the booking and queue the refund.\n\n"
            "— UzWellness"
        ),
    )


def send_cancellation_rejected(*, to: str, booking_code: str) -> None:
    send_email(
        to=to,
        subject=f"Cancellation request declined — {booking_code}",
        body=(
            "Your cancellation request was reviewed and declined by the property.\n\n"
            f"Booking code: {booking_code}\n\n"
            "Your booking remains active. Please contact the property for details.\n\n"
            "— UzWellness"
        ),
    )
