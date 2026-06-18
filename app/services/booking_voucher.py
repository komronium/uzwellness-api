"""Render a downloadable booking-confirmation voucher as a PDF.

Locale-aware (uz/ru/en). Reuses :func:`build_invoice` for the priced line
items / totals and loads the property for the header (address, phones, GPS,
cancellation policy). Generated on demand; nothing is persisted.
"""

from __future__ import annotations

import os
import threading
from datetime import date
from decimal import Decimal
from io import BytesIO

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import pick_locale
from app.models.booking import Booking
from app.models.package import Package
from app.models.program import TreatmentProgram
from app.models.room import Room
from app.models.sanatorium import Sanatorium
from app.services.booking_invoice import build_invoice

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

_FONT = "VoucherSans"
_FONT_BOLD = "VoucherSans-Bold"
_FONT_LOCK = threading.Lock()
_FONTS_READY = False

# Prefer system DejaVu (broad Unicode), fall back to reportlab's bundled Vera
# which always ships with the package — so Cyrillic renders even in the slim
# production image where DejaVu may be absent.
_FONT_CANDIDATES = [
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ),
]


def _ensure_fonts() -> None:
    global _FONTS_READY
    if _FONTS_READY:
        return
    with _FONT_LOCK:
        if _FONTS_READY:
            return
        import reportlab

        bundled = os.path.join(os.path.dirname(reportlab.__file__), "fonts")
        candidates = _FONT_CANDIDATES + [
            (os.path.join(bundled, "Vera.ttf"), os.path.join(bundled, "VeraBd.ttf")),
        ]
        for regular, bold in candidates:
            if os.path.exists(regular) and os.path.exists(bold):
                pdfmetrics.registerFont(TTFont(_FONT, regular))
                pdfmetrics.registerFont(TTFont(_FONT_BOLD, bold))
                pdfmetrics.registerFontFamily(_FONT, normal=_FONT, bold=_FONT_BOLD)
                _FONTS_READY = True
                return
        raise RuntimeError("No Unicode TTF font available for voucher rendering")


_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "title": "Booking confirmation",
        "confirmation_number": "Confirmation number",
        "status": "Status",
        "booking_date": "Booking date",
        "check_in": "Check-in",
        "check_out": "Check-out",
        "nights": "Nights",
        "rooms": "Rooms",
        "guests": "Guests",
        "stay": "Room / program",
        "guest_name": "Guest",
        "price": "Price",
        "description": "Description",
        "amount": "Amount",
        "total": "Total (incl. taxes)",
        "extra_bed": "Extra bed",
        "cancellation": "Cancellation policy",
        "non_refundable": "Non-refundable",
        "free_cancellation": "Free cancellation",
        "free_cancellation_days": (
            "Free cancellation up to {days} day(s) before check-in"
        ),
        "see_policy": "See the property's cancellation policy",
        "address": "Address",
        "phone": "Phone",
        "gps": "GPS",
        "support": "Support",
        "footer": (
            "Present this confirmation at check-in. "
            "Questions? Contact the property directly."
        ),
    },
    "ru": {
        "title": "Подтверждение бронирования",
        "confirmation_number": "Номер подтверждения",
        "status": "Статус",
        "booking_date": "Дата бронирования",
        "check_in": "Заезд",
        "check_out": "Отъезд",
        "nights": "Ночей",
        "rooms": "Номера",
        "guests": "Гостей",
        "stay": "Номер / программа",
        "guest_name": "Гость",
        "price": "Цена",
        "description": "Описание",
        "amount": "Сумма",
        "total": "Итого (включая налоги)",
        "extra_bed": "Доп. кровать",
        "cancellation": "Правила отмены",
        "non_refundable": "Без возврата средств",
        "free_cancellation": "Бесплатная отмена",
        "free_cancellation_days": (
            "Бесплатная отмена не позднее чем за {days} дн. до заезда"
        ),
        "see_policy": "См. правила отмены объекта размещения",
        "address": "Адрес",
        "phone": "Телефон",
        "gps": "GPS",
        "support": "Поддержка",
        "footer": (
            "Предъявите это подтверждение при заезде. "
            "Вопросы? Свяжитесь с объектом размещения напрямую."
        ),
    },
    "uz": {
        "title": "Bron tasdiqlandi",
        "confirmation_number": "Tasdiqlash raqami",
        "status": "Holati",
        "booking_date": "Bron sanasi",
        "check_in": "Kelish",
        "check_out": "Ketish",
        "nights": "Kechalar",
        "rooms": "Xonalar",
        "guests": "Mehmonlar",
        "stay": "Xona / dastur",
        "guest_name": "Mehmon",
        "price": "Narx",
        "description": "Tavsif",
        "amount": "Summa",
        "total": "Jami (soliqlar bilan)",
        "extra_bed": "Qo'shimcha o'rin",
        "cancellation": "Bekor qilish shartlari",
        "non_refundable": "Qaytarilmaydi",
        "free_cancellation": "Bepul bekor qilish",
        "free_cancellation_days": ("Kelishdan {days} kun oldin bepul bekor qilish"),
        "see_policy": "Obyektning bekor qilish shartlariga qarang",
        "address": "Manzil",
        "phone": "Telefon",
        "gps": "GPS",
        "support": "Yordam",
        "footer": (
            "Ushbu tasdiqnomani kelganda ko'rsating. "
            "Savollar? Obyekt bilan bevosita bog'laning."
        ),
    },
}

_STATUS_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "pending": "Pending",
        "confirmed": "Confirmed",
        "cancelled": "Cancelled",
        "completed": "Completed",
    },
    "ru": {
        "pending": "Ожидает",
        "confirmed": "Подтверждено",
        "cancelled": "Отменено",
        "completed": "Завершено",
    },
    "uz": {
        "pending": "Kutilmoqda",
        "confirmed": "Tasdiqlangan",
        "cancelled": "Bekor qilingan",
        "completed": "Yakunlangan",
    },
}


async def build_voucher_pdf(
    db: AsyncSession, booking: Booking, locale: str = "en"
) -> bytes:
    """Render the booking confirmation voucher and return the PDF bytes."""
    _ensure_fonts()
    labels = _LABELS.get(locale, _LABELS["en"])

    invoice = await build_invoice(db, booking)
    sanatorium = await _load_sanatorium(db, booking)
    stay_name = await _stay_name(db, booking, locale)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Booking #{booking.reservation_number}",
    )
    styles = _styles()
    story: list = []

    _append_header(story, styles, labels, booking, sanatorium, invoice, locale)
    _append_confirmation(story, styles, labels, booking, invoice, locale)
    _append_stay(story, styles, labels, invoice, stay_name)
    _append_price(story, styles, labels, invoice)
    _append_cancellation(story, styles, labels, booking, sanatorium, locale)
    _append_footer(story, styles, labels, sanatorium, invoice)

    doc.build(story)
    return buffer.getvalue()


def _styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle(
        "voucher", fontName=_FONT, fontSize=10, leading=14, textColor=colors.black
    )
    return {
        "base": base,
        "title": ParagraphStyle(
            "title", parent=base, fontName=_FONT_BOLD, fontSize=20, leading=24
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base,
            fontName=_FONT_BOLD,
            fontSize=12,
            leading=16,
            spaceBefore=10,
            spaceAfter=4,
        ),
        "muted": ParagraphStyle(
            "muted",
            parent=base,
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#555555"),
        ),
        "big": ParagraphStyle(
            "big", parent=base, fontName=_FONT_BOLD, fontSize=14, leading=18
        ),
        "right": ParagraphStyle("right", parent=base, alignment=TA_RIGHT),
        "right_bold": ParagraphStyle(
            "right_bold", parent=base, fontName=_FONT_BOLD, alignment=TA_RIGHT
        ),
    }


def _append_header(story, styles, labels, booking, sanatorium, invoice, locale) -> None:
    story.append(Paragraph(invoice["sanatorium_name"] or "", styles["title"]))
    lines: list[str] = []
    if sanatorium is not None:
        address = pick_locale(sanatorium.address, locale)
        if address:
            lines.append(f"{labels['address']}: {address}")
        phones = [str(p) for p in (sanatorium.phones or []) if p]
        if phones:
            lines.append(f"{labels['phone']}: {', '.join(phones)}")
        if sanatorium.lat is not None and sanatorium.lng is not None:
            lines.append(f"{labels['gps']}: {sanatorium.lat}, {sanatorium.lng}")
    for line in lines:
        story.append(Paragraph(_esc(line), styles["muted"]))
    story.append(Spacer(1, 8))
    story.append(
        HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#dddddd"))
    )


def _append_confirmation(story, styles, labels, booking, invoice, locale) -> None:
    story.append(Paragraph(labels["title"], styles["h2"]))
    story.append(
        Paragraph(
            f"{labels['confirmation_number']}: <b>{booking.reservation_number}</b>",
            styles["big"],
        )
    )
    status_label = _STATUS_LABELS.get(locale, _STATUS_LABELS["en"]).get(
        booking.status.value, booking.status.value
    )
    rows = [
        [labels["check_in"], _fmt_date(invoice["check_in"])],
        [labels["check_out"], _fmt_date(invoice["check_out"])],
        [labels["nights"], str(invoice["nights"])],
        [labels["rooms"], str(booking.rooms_count)],
        [labels["guests"], str(invoice["guests"])],
        [labels["status"], status_label],
        [labels["booking_date"], _fmt_date(booking.created_at.date())],
    ]
    story.append(_kv_table(rows, styles))


def _append_stay(story, styles, labels, invoice, stay_name) -> None:
    if stay_name:
        story.append(Paragraph(labels["stay"], styles["h2"]))
        story.append(Paragraph(_esc(stay_name), styles["base"]))
    if invoice["customer_name"]:
        story.append(
            Paragraph(
                f"{labels['guest_name']}: {_esc(invoice['customer_name'])}",
                styles["base"],
            )
        )


def _append_price(story, styles, labels, invoice) -> None:
    story.append(Paragraph(labels["price"], styles["h2"]))
    currency = invoice["currency"]
    header = [
        Paragraph(labels["description"], styles["base"]),
        Paragraph(labels["amount"], styles["right"]),
    ]
    data = [header]
    for item in invoice["line_items"]:
        desc = _localize_line(item, labels)
        data.append(
            [
                Paragraph(_esc(desc), styles["base"]),
                Paragraph(_fmt_money(item["amount"], currency), styles["right"]),
            ]
        )
    data.append(
        [
            Paragraph(labels["total"], styles["right_bold"]),
            Paragraph(_fmt_money(invoice["total"], currency), styles["right_bold"]),
        ]
    )
    table = Table(data, colWidths=[115 * mm, 49 * mm])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), _FONT),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#dddddd")),
                ("LINEABOVE", (0, -1), (-1, -1), 0.6, colors.HexColor("#dddddd")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(table)


def _append_cancellation(story, styles, labels, booking, sanatorium, locale) -> None:
    story.append(Paragraph(labels["cancellation"], styles["h2"]))
    story.append(
        Paragraph(
            _esc(_cancellation_text(booking, sanatorium, locale, labels)),
            styles["base"],
        )
    )


def _append_footer(story, styles, labels, sanatorium, invoice) -> None:
    story.append(Spacer(1, 12))
    story.append(
        HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#dddddd"))
    )
    story.append(Spacer(1, 6))
    support = None
    if sanatorium is not None and sanatorium.customer_support_email:
        support = sanatorium.customer_support_email
    elif invoice.get("customer_email"):
        support = invoice["customer_email"]
    if support:
        story.append(
            Paragraph(f"{labels['support']}: {_esc(support)}", styles["muted"])
        )
    story.append(Paragraph(labels["footer"], styles["muted"]))


def _kv_table(rows: list[list[str]], styles) -> Table:
    data = [
        [Paragraph(_esc(k), styles["base"]), Paragraph(_esc(v), styles["base"])]
        for k, v in rows
    ]
    table = Table(data, colWidths=[55 * mm, 109 * mm])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), _FONT),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#555555")),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return table


def _localize_line(item: dict, labels: dict[str, str]) -> str:
    desc = str(item.get("description") or "")
    if desc.startswith("Extra bed"):
        return f"{labels['extra_bed']} × {item.get('qty', 1)}"
    if desc == "Room/program":
        return labels["stay"]
    return desc


def _cancellation_text(booking, sanatorium, locale, labels) -> str:
    if booking.refundable is False:
        return labels["non_refundable"]
    if booking.refundable is True:
        if booking.free_cancellation_days:
            return labels["free_cancellation_days"].format(
                days=booking.free_cancellation_days
            )
        return labels["free_cancellation"]
    if sanatorium is not None:
        text = pick_locale(sanatorium.cancellation_policy, locale)
        if text:
            return text
    return labels["see_policy"]


async def _load_sanatorium(db: AsyncSession, booking: Booking) -> Sanatorium | None:
    sanatorium_id = None
    if booking.room_id is not None:
        sanatorium_id = await db.scalar(
            select(Room.sanatorium_id).where(Room.id == booking.room_id)
        )
    elif booking.program_id is not None:
        sanatorium_id = await db.scalar(
            select(TreatmentProgram.sanatorium_id).where(
                TreatmentProgram.id == booking.program_id
            )
        )
    elif booking.package_id is not None:
        sanatorium_id = await db.scalar(
            select(Package.sanatorium_id).where(Package.id == booking.package_id)
        )
    if sanatorium_id is None:
        return None
    return await db.get(Sanatorium, sanatorium_id)


async def _stay_name(db: AsyncSession, booking: Booking, locale: str) -> str | None:
    name: dict | None = None
    if booking.room_id is not None:
        name = await db.scalar(select(Room.name).where(Room.id == booking.room_id))
    elif booking.program_id is not None:
        name = await db.scalar(
            select(TreatmentProgram.name).where(
                TreatmentProgram.id == booking.program_id
            )
        )
    elif booking.package_id is not None:
        name = await db.scalar(
            select(Package.title).where(Package.id == booking.package_id)
        )
    return (pick_locale(name, locale) or None) if name else None


def _fmt_money(amount, currency: str) -> str:
    value = Decimal(str(amount)).quantize(Decimal("0.01"))
    return f"{currency} {value:,.2f}"


def _fmt_date(value: date) -> str:
    return value.strftime("%d %b %Y")


def _esc(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
