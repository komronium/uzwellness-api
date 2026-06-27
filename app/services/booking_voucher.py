"""Render a downloadable booking-confirmation voucher as a PDF.

Locale-aware (uz/ru/en). Modelled on a Booking.com print voucher: a property
header with GPS, a prominent confirmation box with the check-in / check-out /
rooms / nights grid, a price breakdown, the cancellation policy and a
"need help" footer. Reuses :func:`build_invoice` for the priced line items and
totals. Generated on demand; nothing is persisted.
"""

from __future__ import annotations

import os
import threading
from datetime import date, time
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
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
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

# Brand-ish accents kept subtle so the document still reads as a clean voucher.
_ACCENT = colors.HexColor("#003580")  # Booking-style deep blue
_BOX_BG = colors.HexColor("#f2f6fc")
_RULE = colors.HexColor("#dddddd")
_MUTED = colors.HexColor("#555555")

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
        "confirmation_heading": "Booking confirmation",
        "confirmation_number": "Confirmation number",
        "check_in": "Check-in",
        "check_out": "Check-out",
        "rooms": "Rooms",
        "nights": "Nights",
        "status": "Status",
        "booking_date": "Booking date",
        "guests": "Guests",
        "guest_name": "Guest name",
        "stay": "Your stay",
        "price": "Price",
        "description": "Description",
        "amount": "Amount",
        "total": "Total price (incl. taxes)",
        "extra_bed": "Extra bed",
        "payment": "Payment details",
        "payment_by": "All payments are handled by the property {name}.",
        "cancellation": "Cancellation policy",
        "non_refundable": "Non-refundable",
        "free_cancellation": "Free cancellation",
        "free_cancellation_days": (
            "Free cancellation up to {days} day(s) before check-in"
        ),
        "see_policy": "See the property's cancellation policy",
        "address": "Address",
        "phone": "Phone",
        "gps": "GPS coordinates",
        "need_help": "Need help?",
        "contact_property": (
            "For anything related to your stay, contact {name} directly."
        ),
        "support": "Support",
        "footer": (
            "This printout contains the key details of your booking. "
            "You can present it at check-in."
        ),
    },
    "ru": {
        "confirmation_heading": "Подтверждение бронирования",
        "confirmation_number": "Номер подтверждения",
        "check_in": "Заезд",
        "check_out": "Отъезд",
        "rooms": "Номера",
        "nights": "Ночи",
        "status": "Статус",
        "booking_date": "Дата бронирования",
        "guests": "Число гостей",
        "guest_name": "Имя гостя",
        "stay": "Ваше проживание",
        "price": "Цена",
        "description": "Описание",
        "amount": "Сумма",
        "total": "Итоговая цена (включая налоги)",
        "extra_bed": "Доп. кровать",
        "payment": "Сведения об оплате",
        "payment_by": "Все платежи обрабатывает объект размещения {name}.",
        "cancellation": "Правила отмены",
        "non_refundable": "Без возврата средств",
        "free_cancellation": "Бесплатная отмена",
        "free_cancellation_days": (
            "Бесплатная отмена не позднее чем за {days} дн. до заезда"
        ),
        "see_policy": "См. правила отмены объекта размещения",
        "address": "Адрес",
        "phone": "Телефон",
        "gps": "Координаты GPS",
        "need_help": "Требуется помощь?",
        "contact_property": (
            "По вопросам, связанным с проживанием, свяжитесь с {name} напрямую."
        ),
        "support": "Поддержка",
        "footer": (
            "В этой версии для печати содержится наиболее важная информация о "
            "вашем бронировании. Вы можете предъявить её при заезде."
        ),
    },
    "uz": {
        "confirmation_heading": "Bron tasdiqlangani",
        "confirmation_number": "Tasdiqlash raqami",
        "check_in": "Kelish",
        "check_out": "Ketish",
        "rooms": "Xonalar",
        "nights": "Kechalar",
        "status": "Holati",
        "booking_date": "Bron sanasi",
        "guests": "Mehmonlar soni",
        "guest_name": "Mehmon ismi",
        "stay": "Sizning bandingiz",
        "price": "Narx",
        "description": "Tavsif",
        "amount": "Summa",
        "total": "Yakuniy narx (soliqlar bilan)",
        "extra_bed": "Qo'shimcha o'rin",
        "payment": "To'lov ma'lumotlari",
        "payment_by": "Barcha to'lovlarni obyekt ({name}) o'zi qabul qiladi.",
        "cancellation": "Bekor qilish shartlari",
        "non_refundable": "Qaytarilmaydi",
        "free_cancellation": "Bepul bekor qilish",
        "free_cancellation_days": "Kelishdan {days} kun oldin bepul bekor qilish",
        "see_policy": "Obyektning bekor qilish shartlariga qarang",
        "address": "Manzil",
        "phone": "Telefon",
        "gps": "GPS koordinatalari",
        "need_help": "Yordam kerakmi?",
        "contact_property": (
            "Bandingiz bilan bog'liq savollar bo'lsa, {name} bilan to'g'ridan-to'g'ri "
            "bog'laning."
        ),
        "support": "Yordam",
        "footer": (
            "Ushbu chop etilgan nusxada bandingiz haqidagi eng muhim ma'lumotlar bor. "
            "Uni kelganda ko'rsatishingiz mumkin."
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

_MONTHS: dict[str, list[str]] = {
    "en": [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ],
    "ru": [
        "январь",
        "февраль",
        "март",
        "апрель",
        "май",
        "июнь",
        "июль",
        "август",
        "сентябрь",
        "октябрь",
        "ноябрь",
        "декабрь",
    ],
    "uz": [
        "Yanvar",
        "Fevral",
        "Mart",
        "Aprel",
        "May",
        "Iyun",
        "Iyul",
        "Avgust",
        "Sentabr",
        "Oktabr",
        "Noyabr",
        "Dekabr",
    ],
}

_WEEKDAYS: dict[str, list[str]] = {
    "en": [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ],
    "ru": [
        "понедельник",
        "вторник",
        "среда",
        "четверг",
        "пятница",
        "суббота",
        "воскресенье",
    ],
    "uz": [
        "Dushanba",
        "Seshanba",
        "Chorshanba",
        "Payshanba",
        "Juma",
        "Shanba",
        "Yakshanba",
    ],
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

    _append_header(story, styles, labels, sanatorium, invoice, locale)
    _append_confirmation_box(
        story, styles, labels, booking, sanatorium, invoice, locale
    )
    _append_stay(story, styles, labels, booking, invoice, stay_name, locale)
    _append_price(story, styles, labels, invoice, sanatorium)
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
            spaceBefore=12,
            spaceAfter=4,
            textColor=_ACCENT,
        ),
        "muted": ParagraphStyle(
            "muted", parent=base, fontSize=9, leading=12, textColor=_MUTED
        ),
        "right": ParagraphStyle("right", parent=base, alignment=TA_RIGHT),
        "right_bold": ParagraphStyle(
            "right_bold", parent=base, fontName=_FONT_BOLD, alignment=TA_RIGHT
        ),
        # Confirmation box cells
        "box_label": ParagraphStyle(
            "box_label",
            parent=base,
            fontSize=8,
            leading=10,
            alignment=TA_CENTER,
            textColor=_MUTED,
        ),
        "box_day": ParagraphStyle(
            "box_day",
            parent=base,
            fontName=_FONT_BOLD,
            fontSize=22,
            leading=24,
            alignment=TA_CENTER,
            textColor=_ACCENT,
        ),
        "box_sub": ParagraphStyle(
            "box_sub",
            parent=base,
            fontSize=8,
            leading=10,
            alignment=TA_CENTER,
            textColor=_MUTED,
        ),
        "conf_no": ParagraphStyle(
            "conf_no",
            parent=base,
            fontName=_FONT_BOLD,
            fontSize=15,
            leading=18,
            textColor=_ACCENT,
        ),
    }


def _append_header(story, styles, labels, sanatorium, invoice, locale) -> None:
    story.append(Paragraph(_esc(invoice["sanatorium_name"] or ""), styles["title"]))
    if sanatorium is not None:
        address = pick_locale(sanatorium.address, locale)
        if address:
            story.append(
                Paragraph(f"{labels['address']}: {_esc(address)}", styles["muted"])
            )
        phones = [str(p) for p in (sanatorium.phones or []) if p]
        if phones:
            story.append(
                Paragraph(
                    f"{labels['phone']}: {_esc(', '.join(phones))}", styles["muted"]
                )
            )
        if sanatorium.lat is not None and sanatorium.lng is not None:
            story.append(
                Paragraph(
                    f"{labels['gps']}: {sanatorium.lat}, {sanatorium.lng}",
                    styles["muted"],
                )
            )
    story.append(Spacer(1, 8))


def _append_confirmation_box(
    story, styles, labels, booking, sanatorium, invoice, locale
) -> None:
    heading = Paragraph(labels["confirmation_heading"], styles["box_label"])
    conf_no = Paragraph(
        f"{labels['confirmation_number']}: "
        f"<font name='{_FONT_BOLD}'>{_esc(booking.reservation_number)}</font>",
        styles["conf_no"],
    )

    check_in_time = sanatorium.check_in_time if sanatorium is not None else None
    check_out_time = sanatorium.check_out_time if sanatorium is not None else None
    grid = Table(
        [
            [
                Paragraph(labels["check_in"], styles["box_label"]),
                Paragraph(labels["check_out"], styles["box_label"]),
                Paragraph(labels["rooms"], styles["box_label"]),
                Paragraph(labels["nights"], styles["box_label"]),
            ],
            [
                _date_cell(styles, invoice["check_in"], check_in_time, locale),
                _date_cell(styles, invoice["check_out"], check_out_time, locale),
                Paragraph(str(booking.rooms_count), styles["box_day"]),
                Paragraph(str(invoice["nights"]), styles["box_day"]),
            ],
        ],
        colWidths=[44 * mm, 44 * mm, 38 * mm, 38 * mm],
    )
    grid.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, 0), 2),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
                ("TOPPADDING", (0, 1), (-1, 1), 4),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 6),
                ("LINEAFTER", (0, 0), (-2, -1), 0.5, _RULE),
            ]
        )
    )

    inner = [[heading], [conf_no], [grid]]
    box = Table(inner, colWidths=[164 * mm])
    box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _BOX_BG),
                ("BOX", (0, 0), (-1, -1), 0.8, _ACCENT),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, 0), 8),
                ("TOPPADDING", (0, 2), (-1, 2), 4),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 8),
            ]
        )
    )
    story.append(box)


def _date_cell(styles, value: date, t: time | None, locale: str) -> Table:
    months = _MONTHS.get(locale, _MONTHS["en"])
    weekdays = _WEEKDAYS.get(locale, _WEEKDAYS["en"])
    rows = [
        [Paragraph(str(value.day), styles["box_day"])],
        [Paragraph(_esc(months[value.month - 1]), styles["box_sub"])],
        [Paragraph(_esc(weekdays[value.weekday()]), styles["box_sub"])],
    ]
    if t is not None:
        rows.append([Paragraph(t.strftime("%H:%M"), styles["box_sub"])])
    cell = Table(rows, colWidths=[40 * mm])
    cell.setStyle(
        TableStyle(
            [
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]
        )
    )
    return cell


def _append_stay(story, styles, labels, booking, invoice, stay_name, locale) -> None:
    story.append(Paragraph(labels["stay"], styles["h2"]))
    if stay_name:
        story.append(Paragraph(_esc(stay_name), styles["base"]))
    guest_names = _guest_names(booking) or (
        [invoice["customer_name"]] if invoice["customer_name"] else []
    )
    rows: list[list[str]] = []
    if guest_names:
        rows.append([labels["guest_name"], ", ".join(guest_names)])
    rows.append([labels["guests"], str(invoice["guests"])])
    status_label = _STATUS_LABELS.get(locale, _STATUS_LABELS["en"]).get(
        booking.status.value, booking.status.value
    )
    rows.append([labels["status"], status_label])
    rows.append([labels["booking_date"], _fmt_date(booking.created_at.date())])
    story.append(_kv_table(rows, styles))


def _append_price(story, styles, labels, invoice, sanatorium) -> None:
    story.append(Paragraph(labels["price"], styles["h2"]))
    currency = invoice["currency"]
    data = [
        [
            Paragraph(labels["description"], styles["base"]),
            Paragraph(labels["amount"], styles["right"]),
        ]
    ]
    for item in invoice["line_items"]:
        data.append(
            [
                Paragraph(_esc(_localize_line(item, labels)), styles["base"]),
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
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, _RULE),
                ("LINEABOVE", (0, -1), (-1, -1), 0.6, _RULE),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(table)
    name = invoice["sanatorium_name"]
    if name:
        story.append(Spacer(1, 4))
        story.append(
            Paragraph(_esc(labels["payment_by"].format(name=name)), styles["muted"])
        )


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
    story.append(HRFlowable(width="100%", thickness=0.6, color=_RULE))
    story.append(Spacer(1, 4))
    story.append(Paragraph(labels["need_help"], styles["h2"]))
    name = invoice["sanatorium_name"]
    if name:
        story.append(
            Paragraph(
                _esc(labels["contact_property"].format(name=name)), styles["muted"]
            )
        )
    support = None
    if sanatorium is not None and sanatorium.customer_support_email:
        support = sanatorium.customer_support_email
    if support:
        story.append(
            Paragraph(f"{labels['support']}: {_esc(support)}", styles["muted"])
        )
    story.append(Spacer(1, 4))
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
                ("TEXTCOLOR", (0, 0), (0, -1), _MUTED),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return table


def _guest_names(booking: Booking) -> list[str]:
    names: list[str] = []
    for entry in booking.guest_details or []:
        if isinstance(entry, dict):
            name = entry.get("full_name") or entry.get("name")
            if name:
                names.append(str(name))
    return names


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
