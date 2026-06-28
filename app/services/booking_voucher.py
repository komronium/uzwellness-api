"""Render a downloadable booking-confirmation voucher as a PDF.

Locale-aware (uz/ru/en, defaults to en). Modelled closely on a Booking.com print
voucher: a header band (brand + confirmation number), a bordered top block with
the property photo, address, GPS and a check-in / check-out / rooms / nights
grid, the price breakdown, what's included (board + treatment program), a map,
the room block with amenities and cancellation policy, and a "need help" footer.

External assets (property photo, static map) are fetched best-effort and skipped
on any failure, so the voucher always renders.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import threading
from dataclasses import dataclass, field
from datetime import date, time
from decimal import Decimal
from io import BytesIO

import httpx
from PIL import Image as PILImage
from PIL import ImageDraw
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.storage import url_to_key
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
    Image as RLImage,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger("uzwellness.voucher")

_FONT = "VoucherSans"
_FONT_BOLD = "VoucherSans-Bold"
_FONT_LOCK = threading.Lock()
_FONTS_READY = False

_ACCENT = colors.HexColor("#003580")  # deep blue
_BOX_BG = colors.HexColor("#f2f6fc")
_RULE = colors.HexColor("#dcdcdc")
_MUTED = colors.HexColor("#555555")
_RED = colors.HexColor("#cc0000")

_CONTENT_W = 174 * mm  # A4 width (210) minus 18mm margins each side

# Prefer the Ubuntu font (modern, clean, Latin+Cyrillic) when present, then
# DejaVu, then reportlab's bundled Vera as a last resort.
_FONT_CANDIDATES = [
    (
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    ),
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
        override = (
            [(settings.VOUCHER_FONT_PATH, settings.VOUCHER_FONT_BOLD_PATH)]
            if settings.VOUCHER_FONT_PATH and settings.VOUCHER_FONT_BOLD_PATH
            else []
        )
        candidates = (
            override
            + _FONT_CANDIDATES
            + [(os.path.join(bundled, "Vera.ttf"), os.path.join(bundled, "VeraBd.ttf"))]
        )
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
        "guests_heading": "Guests",
        "guest_no": "#",
        "guest_name": "Guest name",
        "passport": "Passport",
        "no_program": "—",
        "price": "Price",
        "description": "Description",
        "amount": "Amount",
        "total": "Total price (incl. taxes)",
        "total_note": "The total shown is the amount you pay the property.",
        "fees_note": (
            "Any optional on-site services are paid directly at the property."
        ),
        "extra_bed": "Extra bed",
        "payment": "Payment details",
        "payment_by": "All payments are handled by the property {name}.",
        "payment_methods": "Accepted payment methods: {methods}.",
        "included": "What's included",
        "accommodation": "Accommodation: {nights} night(s), {board}",
        "treatment_program": "Treatment program",
        "amenities": "Room facilities",
        "board": "Board",
        "stay_line": "Accommodation — {nights} night(s)",
        "per_night": "≈ {amount} / night",
        "cancellation": "Cancellation policy",
        "prepayment": "Prepayment",
        "prepayment_not_required": "No prepayment needed.",
        "non_refundable": "Non-refundable",
        "free_cancellation": "Free cancellation",
        "free_cancellation_days": (
            "Free cancellation up to {days} day(s) before check-in"
        ),
        "penalty": "Cancellation fee: {amount}",
        "see_policy": "See the property's cancellation policy",
        "address": "Address",
        "phone": "Phone",
        "gps": "GPS",
        "important_info": "Important information",
        "house_rules": "House rules",
        "checkin_from": "Check-in from {t}",
        "checkout_until": "Check-out until {t}",
        "pets_allowed": "Pets allowed",
        "pets_not_allowed": "Pets are not allowed",
        "need_help": "Need help?",
        "contact_property": (
            "For anything related to your stay, contact {name} directly."
        ),
        "support": "Support",
        "footer": (
            "This printout contains the key details of your booking. "
            "You can present it at check-in."
        ),
        "sleeps": "Sleeps {n}",
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
        "guests": "Гостей",
        "guests_heading": "Гости",
        "guest_no": "№",
        "guest_name": "Имя гостя",
        "passport": "Паспорт",
        "no_program": "—",
        "price": "Цена",
        "description": "Описание",
        "amount": "Сумма",
        "total": "Итоговая цена (включая налоги)",
        "total_note": "Указанная итоговая цена — это сумма, которую вы платите объекту.",
        "fees_note": (
            "Дополнительные услуги на месте (при наличии) оплачиваются в объекте."
        ),
        "extra_bed": "Доп. кровать",
        "payment": "Сведения об оплате",
        "payment_by": "Все платежи обрабатывает объект размещения {name}.",
        "payment_methods": "Доступные способы оплаты: {methods}.",
        "included": "Что включено",
        "accommodation": "Проживание: {nights} ноч., {board}",
        "treatment_program": "Лечебная программа",
        "amenities": "Удобства номера",
        "board": "Питание",
        "stay_line": "Проживание — {nights} ноч.",
        "per_night": "≈ {amount} / ночь",
        "cancellation": "Правила отмены",
        "prepayment": "Предоплата",
        "prepayment_not_required": "Предоплата не требуется.",
        "non_refundable": "Без возврата средств",
        "free_cancellation": "Бесплатная отмена",
        "free_cancellation_days": (
            "Бесплатная отмена не позднее чем за {days} дн. до заезда"
        ),
        "penalty": "Стоимость отмены: {amount}",
        "see_policy": "См. правила отмены объекта размещения",
        "address": "Адрес",
        "phone": "Телефон",
        "gps": "Координаты GPS",
        "important_info": "Важная информация",
        "house_rules": "Порядок проживания",
        "checkin_from": "Заезд с {t}",
        "checkout_until": "Отъезд до {t}",
        "pets_allowed": "Размещение с питомцами разрешено",
        "pets_not_allowed": "Размещение с питомцами запрещено",
        "need_help": "Требуется помощь?",
        "contact_property": (
            "По вопросам, связанным с проживанием, свяжитесь с {name} напрямую."
        ),
        "support": "Поддержка",
        "footer": (
            "В этой версии для печати содержится наиболее важная информация о "
            "вашем бронировании. Вы можете предъявить её при заезде."
        ),
        "sleeps": "Вместимость: {n}",
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
        "guests": "Mehmonlar",
        "guests_heading": "Mehmonlar",
        "guest_no": "№",
        "guest_name": "Mehmon ismi",
        "passport": "Pasport",
        "no_program": "—",
        "price": "Narx",
        "description": "Tavsif",
        "amount": "Summa",
        "total": "Yakuniy narx (soliqlar bilan)",
        "total_note": "Ko'rsatilgan yakuniy narx — siz obyektga to'laydigan summa.",
        "fees_note": (
            "Joyida ko'rsatiladigan qo'shimcha xizmatlar (bo'lsa) obyektda to'lanadi."
        ),
        "extra_bed": "Qo'shimcha o'rin",
        "payment": "To'lov ma'lumotlari",
        "payment_by": "Barcha to'lovlarni obyekt ({name}) o'zi qabul qiladi.",
        "payment_methods": "Qabul qilinadigan to'lov turlari: {methods}.",
        "included": "Nimalar kiritilgan",
        "accommodation": "Yashash: {nights} kecha, {board}",
        "treatment_program": "Davolash dasturi",
        "amenities": "Xona qulayliklari",
        "board": "Ovqatlanish",
        "stay_line": "Yashash — {nights} kecha",
        "per_night": "≈ {amount} / kecha",
        "cancellation": "Bekor qilish shartlari",
        "prepayment": "Oldindan to'lov",
        "prepayment_not_required": "Oldindan to'lov talab qilinmaydi.",
        "non_refundable": "Qaytarilmaydi",
        "free_cancellation": "Bepul bekor qilish",
        "free_cancellation_days": "Kelishdan {days} kun oldin bepul bekor qilish",
        "penalty": "Bekor qilish to'lovi: {amount}",
        "see_policy": "Obyektning bekor qilish shartlariga qarang",
        "address": "Manzil",
        "phone": "Telefon",
        "gps": "GPS",
        "important_info": "Muhim ma'lumot",
        "house_rules": "Yashash tartibi",
        "checkin_from": "Kelish {t} dan",
        "checkout_until": "Ketish {t} gacha",
        "pets_allowed": "Uy hayvonlari bilan ruxsat",
        "pets_not_allowed": "Uy hayvonlari bilan taqiqlanadi",
        "need_help": "Yordam kerakmi?",
        "contact_property": (
            "Bandingiz bo'yicha savollar bo'lsa, {name} bilan bevosita bog'laning."
        ),
        "support": "Yordam",
        "footer": (
            "Ushbu chop etilgan nusxada bandingiz haqidagi eng muhim ma'lumotlar bor. "
            "Uni kelganda ko'rsatishingiz mumkin."
        ),
        "sleeps": "Sig'imi: {n}",
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

_BOARD_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "room_only": "room only",
        "breakfast": "breakfast included",
        "half_board": "half board (2 meals)",
        "full_board": "full board (3 meals)",
        "all_inclusive": "all inclusive",
    },
    "ru": {
        "room_only": "без питания",
        "breakfast": "завтрак включён",
        "half_board": "полупансион (2 приёма)",
        "full_board": "полный пансион (3 приёма)",
        "all_inclusive": "всё включено",
    },
    "uz": {
        "room_only": "ovqatsiz",
        "breakfast": "nonushta bilan",
        "half_board": "yarim pansion (2 mahal)",
        "full_board": "to'liq pansion (3 mahal)",
        "all_inclusive": "hammasi kiritilgan",
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
        "января",
        "февраля",
        "марта",
        "апреля",
        "мая",
        "июня",
        "июля",
        "августа",
        "сентября",
        "октября",
        "ноября",
        "декабря",
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


@dataclass(slots=True)
class _Ctx:
    sanatorium: Sanatorium | None
    room: Room | None
    invoice: dict
    stay_name: str | None
    photo: bytes | None
    map_image: bytes | None
    amenities: list[str] = field(default_factory=list)


async def build_voucher_pdf(
    db: AsyncSession, booking: Booking, locale: str = "en"
) -> bytes:
    """Render the booking confirmation voucher and return the PDF bytes."""
    _ensure_fonts()
    lang = locale if locale in _LABELS else "en"
    labels = _LABELS[lang]

    ctx = await _load_context(db, booking, lang)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"Booking #{booking.reservation_number}",
    )
    styles = _styles()
    story: list = []

    _append_header_band(story, styles, labels, booking)
    _append_top_box(story, styles, labels, booking, ctx, lang)
    _append_room_box(story, styles, labels, booking, ctx, lang)
    _append_guests(story, styles, labels, booking, ctx, lang)
    _append_price(story, styles, labels, booking, ctx)
    _append_map(story, ctx)
    _append_extras(story, styles, labels, ctx, lang)
    _append_footer(story, styles, labels, ctx)

    doc.build(story)
    return buffer.getvalue()


def _styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle(
        "v", fontName=_FONT, fontSize=9.5, leading=13, textColor=colors.black
    )
    return {
        "base": base,
        "brand": ParagraphStyle(
            "brand", parent=base, fontName=_FONT_BOLD, fontSize=22, textColor=_ACCENT
        ),
        "conf_label": ParagraphStyle(
            "conf_label", parent=base, fontSize=10, alignment=TA_RIGHT
        ),
        "conf_head": ParagraphStyle(
            "conf_head",
            parent=base,
            fontName=_FONT_BOLD,
            fontSize=14,
            alignment=TA_RIGHT,
        ),
        "conf_num": ParagraphStyle(
            "conf_num",
            parent=base,
            fontName=_FONT_BOLD,
            fontSize=12,
            alignment=TA_RIGHT,
            textColor=_ACCENT,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base,
            fontName=_FONT_BOLD,
            fontSize=12.5,
            leading=16,
            spaceBefore=12,
            spaceAfter=5,
            textColor=_ACCENT,
        ),
        "name": ParagraphStyle(
            "name", parent=base, fontName=_FONT_BOLD, fontSize=13, leading=16
        ),
        "muted": ParagraphStyle(
            "muted", parent=base, fontSize=9, leading=12, textColor=_MUTED
        ),
        "right": ParagraphStyle("right", parent=base, alignment=TA_RIGHT),
        "right_bold": ParagraphStyle(
            "right_bold", parent=base, fontName=_FONT_BOLD, alignment=TA_RIGHT
        ),
        "big_total": ParagraphStyle(
            "big_total",
            parent=base,
            fontName=_FONT_BOLD,
            fontSize=15,
            alignment=TA_RIGHT,
        ),
        "total_label": ParagraphStyle(
            "total_label",
            parent=base,
            fontName=_FONT_BOLD,
            fontSize=12,
            textColor=_ACCENT,
        ),
        "total_amount": ParagraphStyle(
            "total_amount",
            parent=base,
            fontName=_FONT_BOLD,
            fontSize=14,
            leading=18,
            alignment=TA_RIGHT,
            textColor=_ACCENT,
        ),
        "grid_label": ParagraphStyle(
            "grid_label",
            parent=base,
            fontSize=7.5,
            leading=9,
            alignment=TA_CENTER,
            textColor=_MUTED,
        ),
        "grid_day": ParagraphStyle(
            "grid_day",
            parent=base,
            fontName=_FONT_BOLD,
            fontSize=22,
            leading=24,
            alignment=TA_CENTER,
            textColor=_ACCENT,
        ),
        "grid_sub": ParagraphStyle(
            "grid_sub",
            parent=base,
            fontSize=7.5,
            leading=9.5,
            alignment=TA_CENTER,
            textColor=_MUTED,
        ),
        "th": ParagraphStyle(
            "th",
            parent=base,
            fontName=_FONT_BOLD,
            fontSize=9,
            textColor=colors.white,
        ),
        "td": ParagraphStyle("td", parent=base, fontSize=9, leading=12),
        "td_small": ParagraphStyle(
            "td_small", parent=base, fontSize=7.5, leading=9.5, textColor=_MUTED
        ),
        "red": ParagraphStyle("red", parent=base, textColor=_RED),
    }


# ── header band ───────────────────────────────────────────────────────────────


def _append_header_band(story, styles, labels, booking) -> None:
    brand = Paragraph(_esc(settings.VOUCHER_BRAND_NAME), styles["brand"])
    right = [
        Paragraph(labels["confirmation_heading"], styles["conf_head"]),
        Paragraph(
            f"{labels['confirmation_number']}: {_esc(booking.reservation_number)}",
            styles["conf_num"],
        ),
    ]
    table = Table([[brand, right]], colWidths=[_CONTENT_W * 0.45, _CONTENT_W * 0.55])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 8))


# ── top box: property + check-in grid ────────────────────────────────────────


def _append_top_box(story, styles, labels, booking, ctx, lang) -> None:
    left_cells: list = []
    if ctx.photo is not None:
        img = _rl_image(ctx.photo, 42 * mm, 28 * mm)
        if img is not None:
            left_cells.append(img)
            left_cells.append(Spacer(1, 4))
    left_cells.append(
        Paragraph(_esc(ctx.invoice["sanatorium_name"] or ""), styles["name"])
    )
    if ctx.sanatorium is not None:
        address = pick_locale(ctx.sanatorium.address, lang)
        if address:
            left_cells.append(
                Paragraph(
                    f"<b>{labels['address']}:</b> {_esc(address)}", styles["muted"]
                )
            )
        phones = [str(p) for p in (ctx.sanatorium.phones or []) if p]
        if phones:
            left_cells.append(
                Paragraph(
                    f"<b>{labels['phone']}:</b> {_esc(', '.join(phones))}",
                    styles["muted"],
                )
            )
        if ctx.sanatorium.lat is not None and ctx.sanatorium.lng is not None:
            left_cells.append(
                Paragraph(
                    f"<b>{labels['gps']}:</b> "
                    f"{ctx.sanatorium.lat}, {ctx.sanatorium.lng}",
                    styles["muted"],
                )
            )

    grid = _date_grid(styles, labels, booking, ctx, lang)
    box = Table([[left_cells, grid]], colWidths=[_CONTENT_W * 0.46, _CONTENT_W * 0.54])
    box.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.8, _RULE),
                ("LINEAFTER", (0, 0), (0, 0), 0.8, _RULE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    story.append(box)


def _date_grid(styles, labels, booking, ctx, lang) -> Table:
    ci_time = ctx.sanatorium.check_in_time if ctx.sanatorium else None
    co_time = ctx.sanatorium.check_out_time if ctx.sanatorium else None
    header = [
        Paragraph(labels["check_in"], styles["grid_label"]),
        Paragraph(labels["check_out"], styles["grid_label"]),
        Paragraph(labels["rooms"], styles["grid_label"]),
        Paragraph(labels["nights"], styles["grid_label"]),
    ]
    values = [
        _date_cell(styles, ctx.invoice["check_in"], ci_time, lang),
        _date_cell(styles, ctx.invoice["check_out"], co_time, lang),
        Paragraph(str(booking.rooms_count), styles["grid_day"]),
        Paragraph(str(ctx.invoice["nights"]), styles["grid_day"]),
    ]
    # Date cells need more room (weekday names); rooms/nights are single digits.
    usable = _CONTENT_W * 0.54 - 20
    wide = usable * 0.3
    narrow = usable * 0.2
    grid = Table([header, values], colWidths=[wide, wide, narrow, narrow])
    grid.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("LINEAFTER", (0, 0), (-2, -1), 0.5, _RULE),
                ("TOPPADDING", (0, 0), (-1, 0), 0),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 3),
                ("TOPPADDING", (0, 1), (-1, 1), 0),
            ]
        )
    )
    return grid


def _date_cell(styles, value: date, t: time | None, lang: str) -> Table:
    months = _MONTHS.get(lang, _MONTHS["en"])
    weekdays = _WEEKDAYS.get(lang, _WEEKDAYS["en"])
    rows = [
        [Paragraph(str(value.day), styles["grid_day"])],
        [Paragraph(_esc(months[value.month - 1]), styles["grid_sub"])],
        [Paragraph(_esc(weekdays[value.weekday()]), styles["grid_sub"])],
    ]
    if t is not None:
        rows.append([Paragraph(t.strftime("%H:%M"), styles["grid_sub"])])
    cell = Table(rows)
    cell.setStyle(
        TableStyle(
            [
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return cell


# ── guests table (name / passport / treatment) ───────────────────────────────


def _append_guests(story, styles, labels, booking, ctx, lang) -> None:
    rows = _guest_rows(booking, ctx, lang)
    if not rows:
        return
    story.append(Paragraph(labels["guests_heading"], styles["h2"]))
    header = [
        Paragraph(labels["guest_no"], styles["th"]),
        Paragraph(labels["guest_name"], styles["th"]),
        Paragraph(labels["passport"], styles["th"]),
        Paragraph(labels["treatment_program"], styles["th"]),
    ]
    data = [header]
    for idx, (name, passport, title, detail) in enumerate(rows, start=1):
        program_cell: list = [Paragraph(f"<b>{_esc(title)}</b>", styles["td"])]
        if detail:
            program_cell.append(Paragraph(_esc(detail), styles["td_small"]))
        data.append(
            [
                Paragraph(str(idx), styles["td"]),
                Paragraph(_esc(name), styles["td"]),
                Paragraph(_esc(passport), styles["td"]),
                program_cell,
            ]
        )
    table = Table(
        data,
        colWidths=[
            10 * mm,
            _CONTENT_W * 0.30,
            _CONTENT_W * 0.24,
            _CONTENT_W - 10 * mm - _CONTENT_W * 0.54,
        ],
    )
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), _ACCENT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, _RULE),
        ("BOX", (0, 0), (-1, -1), 0.6, _RULE),
    ]
    for r in range(1, len(data)):
        if r % 2 == 0:
            style.append(("BACKGROUND", (0, r), (-1, r), _BOX_BG))
    table.setStyle(TableStyle(style))
    story.append(table)


def _guest_rows(booking, ctx, lang) -> list[tuple[str, str, str, str]]:
    """Rows of (name, passport, program_title, program_detail) per guest."""
    labels = _LABELS[lang]
    dash = labels["no_program"]
    treatments = _guest_treatments(booking)
    fallback = ("", "")
    if not any(t[0] for t in treatments) and booking.program_id is not None:
        fallback = (ctx.stay_name or "", "")

    def pick(i: int) -> tuple[str, str]:
        title, detail = treatments[i] if i < len(treatments) else ("", "")
        if not title:
            title, detail = fallback
        return (title or dash, detail)

    rows: list[tuple[str, str, str, str]] = []
    details = booking.guest_details or []
    if details:
        for i, gd in enumerate(details):
            name = (gd.get("full_name") if isinstance(gd, dict) else None) or dash
            passport = (gd.get("passport") if isinstance(gd, dict) else None) or dash
            title, detail = pick(i)
            rows.append((name, passport, title, detail))
    elif ctx.invoice["customer_name"]:
        title, detail = pick(0)
        rows.append((ctx.invoice["customer_name"], dash, title, detail))
    return rows


def _guest_treatments(booking) -> list[tuple[str, str]]:
    """Per-guest (title, detail) treatment from the offer snapshot, in order."""
    snapshot = booking.offer_snapshot or {}
    inclusions = snapshot.get("inclusions") or []

    def _key(entry: dict):
        guest = entry.get("guest") or {}
        return (entry.get("room_index", 0), guest.get("guest_index", 0))

    out: list[tuple[str, str]] = []
    for entry in sorted(inclusions, key=_key):
        title, detail = "", ""
        for item in entry.get("items") or []:
            if item.get("type") in ("treatment", "special_package"):
                title = (item.get("title") or "").strip()
                detail = (item.get("description") or "").strip()
                if title:
                    break
        out.append((title, detail))
    return out


# ── price ─────────────────────────────────────────────────────────────────────


def _append_price(story, styles, labels, booking, ctx) -> None:
    story.append(Paragraph(labels["price"], styles["h2"]))
    currency = ctx.invoice["currency"]
    nights = max(ctx.invoice["nights"], 1)
    data = [
        [
            Paragraph(labels["description"], styles["base"]),
            Paragraph(labels["amount"], styles["right"]),
        ]
    ]
    for item in ctx.invoice["line_items"]:
        desc = str(item.get("description") or "")
        if desc == "Room/program":
            per_night = (Decimal(str(item["amount"])) / nights).quantize(
                Decimal("0.01")
            )
            cell: list = [
                Paragraph(
                    f"<b>{_esc(labels['stay_line'].format(nights=nights))}</b>",
                    styles["base"],
                ),
                Paragraph(
                    labels["per_night"].format(amount=_fmt_money(per_night, currency)),
                    styles["td_small"],
                ),
            ]
        else:
            cell = [Paragraph(_esc(_localize_line(item, labels, ctx)), styles["base"])]
        data.append(
            [cell, Paragraph(_fmt_money(item["amount"], currency), styles["right"])]
        )
    table = Table(data, colWidths=[_CONTENT_W - 50 * mm, 50 * mm])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), _FONT),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, _RULE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(table)

    # Total bar — full width, label left, amount right, with enough room so a
    # long currency amount (e.g. UZS millions) never wraps.
    total_bar = Table(
        [
            [
                Paragraph(labels["total"], styles["total_label"]),
                Paragraph(
                    _fmt_money(ctx.invoice["total"], currency), styles["total_amount"]
                ),
            ]
        ],
        colWidths=[_CONTENT_W * 0.5, _CONTENT_W * 0.5],
    )
    total_bar.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _BOX_BG),
                ("LINEABOVE", (0, 0), (-1, 0), 1.0, _ACCENT),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    story.append(total_bar)
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"<b>{_esc(labels['total_note'])}</b>", styles["base"]))
    notes: list[str] = [labels["fees_note"]]
    name = ctx.invoice["sanatorium_name"]
    if name:
        notes.append(labels["payment_by"].format(name=name))
    methods = _payment_methods(ctx)
    if methods:
        notes.append(labels["payment_methods"].format(methods=methods))
    story.append(Spacer(1, 2))
    story.append(Paragraph(_esc(" ".join(notes)), styles["muted"]))


# ── map ───────────────────────────────────────────────────────────────────────


def _append_map(story, ctx) -> None:
    if ctx.map_image is None:
        return
    img = _rl_image(ctx.map_image, _CONTENT_W, 52 * mm)
    if img is None:
        return
    story.append(Spacer(1, 10))
    story.append(img)


# ── room block: details + cancellation ───────────────────────────────────────


def _append_room_box(story, styles, labels, booking, ctx, lang) -> None:
    # Service / room type as the heading, then board and room facilities.
    left: list = [
        Paragraph(_esc(ctx.stay_name or labels["description"]), styles["name"])
    ]
    board = _board_label(booking.board, lang)
    nights = ctx.invoice["nights"]
    if board:
        left.append(
            Paragraph(
                f"<b>{labels['board']}:</b> {_esc(board)} · {nights} "
                f"{labels['nights'].lower()}",
                styles["base"],
            )
        )
    if ctx.amenities:
        left.append(Spacer(1, 4))
        left.append(
            Paragraph(
                f"<b>{labels['amenities']}:</b> " + _esc(" • ".join(ctx.amenities)),
                styles["muted"],
            )
        )

    right: list = [Paragraph(labels["cancellation"], styles["name"])]
    right.append(
        Paragraph(
            f"<b>{labels['prepayment']}:</b> {labels['prepayment_not_required']}"
            if booking.payment_timing != "prepayment"
            else f"<b>{labels['prepayment']}</b>",
            styles["base"],
        )
    )
    right.append(
        Paragraph(
            _esc(_cancellation_text(booking, ctx.sanatorium, lang, labels)),
            styles["base"],
        )
    )

    box = Table([[left, right]], colWidths=[_CONTENT_W * 0.58, _CONTENT_W * 0.42])
    box.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.8, _RULE),
                ("LINEAFTER", (0, 0), (0, 0), 0.8, _RULE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    story.append(Spacer(1, 10))
    story.append(box)


# ── important info / house rules ─────────────────────────────────────────────


def _append_extras(story, styles, labels, ctx, lang) -> None:
    if ctx.sanatorium is None:
        return
    left: list = []
    house_rules_text = pick_locale(ctx.sanatorium.house_rules, lang)
    if house_rules_text:
        left.append(Paragraph(labels["important_info"], styles["h2"]))
        left.append(Paragraph(_esc(house_rules_text), styles["base"]))

    rules = _house_rule_lines(ctx.sanatorium, labels)
    right: list = []
    if rules:
        right.append(Paragraph(labels["house_rules"], styles["h2"]))
        for line in rules:
            right.append(Paragraph(f"•&nbsp; {_esc(line)}", styles["base"]))

    if not left and not right:
        return
    table = Table([[left, right]], colWidths=[_CONTENT_W * 0.5, _CONTENT_W * 0.5])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (0, 0), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), 12),
                ("LEFTPADDING", (1, 0), (1, 0), 12),
            ]
        )
    )
    story.append(table)


def _house_rule_lines(sanatorium: Sanatorium, labels) -> list[str]:
    lines: list[str] = []
    if sanatorium.check_in_time is not None:
        lines.append(
            labels["checkin_from"].format(t=sanatorium.check_in_time.strftime("%H:%M"))
        )
    if sanatorium.check_out_time is not None:
        lines.append(
            labels["checkout_until"].format(
                t=sanatorium.check_out_time.strftime("%H:%M")
            )
        )
    if sanatorium.pets_allowed is True:
        lines.append(labels["pets_allowed"])
    elif sanatorium.pets_allowed is False:
        lines.append(labels["pets_not_allowed"])
    return lines


# ── footer ────────────────────────────────────────────────────────────────────


def _append_footer(story, styles, labels, ctx) -> None:
    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=0.6, color=_RULE))
    story.append(Spacer(1, 4))
    story.append(Paragraph(labels["need_help"], styles["h2"]))
    name = ctx.invoice["sanatorium_name"]
    if name:
        story.append(
            Paragraph(
                _esc(labels["contact_property"].format(name=name)), styles["muted"]
            )
        )
    if ctx.sanatorium is not None and ctx.sanatorium.customer_support_email:
        story.append(
            Paragraph(
                f"{labels['support']}: {_esc(ctx.sanatorium.customer_support_email)}",
                styles["muted"],
            )
        )
    story.append(Spacer(1, 4))
    story.append(Paragraph(labels["footer"], styles["muted"]))


# ── data loading ──────────────────────────────────────────────────────────────


async def _load_context(db: AsyncSession, booking: Booking, lang: str) -> _Ctx:
    invoice = await build_invoice(db, booking)
    sanatorium = await _load_sanatorium(db, booking)
    room = await _load_room(db, booking)
    stay_name = await _stay_name(db, booking, lang)
    amenities = [pick_locale(a.name, lang) for a in room.amenities][:14] if room else []
    amenities = [a for a in amenities if a]

    photo = await _fetch_photo(sanatorium)
    map_image = await _fetch_map(sanatorium)

    return _Ctx(
        sanatorium=sanatorium,
        room=room,
        invoice=invoice,
        stay_name=stay_name,
        photo=photo,
        map_image=map_image,
        amenities=amenities,
    )


async def _load_sanatorium(db: AsyncSession, booking: Booking) -> Sanatorium | None:
    sanatorium_id = await _sanatorium_id(db, booking)
    if sanatorium_id is None:
        return None
    return await db.scalar(
        select(Sanatorium)
        .options(selectinload(Sanatorium.images))
        .where(Sanatorium.id == sanatorium_id)
    )


async def _sanatorium_id(db: AsyncSession, booking: Booking):
    if booking.room_id is not None:
        return await db.scalar(
            select(Room.sanatorium_id).where(Room.id == booking.room_id)
        )
    if booking.program_id is not None:
        return await db.scalar(
            select(TreatmentProgram.sanatorium_id).where(
                TreatmentProgram.id == booking.program_id
            )
        )
    if booking.package_id is not None:
        return await db.scalar(
            select(Package.sanatorium_id).where(Package.id == booking.package_id)
        )
    return None


async def _load_room(db: AsyncSession, booking: Booking) -> Room | None:
    room_id = booking.room_id
    if room_id is None and booking.package_id is not None:
        room_id = await db.scalar(
            select(Package.room_id).where(Package.id == booking.package_id)
        )
    if room_id is None:
        return None
    return await db.scalar(
        select(Room).options(selectinload(Room.amenities)).where(Room.id == room_id)
    )


async def _stay_name(db: AsyncSession, booking: Booking, lang: str) -> str | None:
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
    return (pick_locale(name, lang) or None) if name else None


# ── external assets (best-effort) ────────────────────────────────────────────


async def _fetch_photo(sanatorium: Sanatorium | None) -> bytes | None:
    if sanatorium is None:
        return None
    images = sanatorium.images or []
    if not images:
        return None
    primary = next((i for i in images if i.is_primary), images[0])
    url = primary.url
    if not url:
        return None
    try:
        if url.startswith("http"):
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.content
        path = os.path.join(settings.UPLOAD_DIR, url_to_key(url))
        if os.path.exists(path):
            with open(path, "rb") as fh:
                return fh.read()
    except Exception:
        logger.warning("voucher: failed to load property photo %s", url)
    return None


async def _fetch_map(sanatorium: Sanatorium | None) -> bytes | None:
    if sanatorium is None or sanatorium.lat is None or sanatorium.lng is None:
        return None
    try:
        return await _render_tile_map(float(sanatorium.lat), float(sanatorium.lng))
    except Exception:
        logger.warning("voucher: failed to render map")
        return None


async def _render_tile_map(
    lat: float, lng: float, *, width: int = 660, height: int = 280
) -> bytes | None:
    """Stitch a static map from OSM tiles and draw a marker at the point."""
    zoom = settings.VOUCHER_MAP_ZOOM
    n = 2**zoom
    x = (lng + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    cx_px, cy_px = x * 256.0, y * 256.0
    left, top = cx_px - width / 2, cy_px - height / 2
    x0, x1 = int(left // 256), int((left + width) // 256)
    y0, y1 = int(top // 256), int((top + height) // 256)

    headers = {"User-Agent": f"{settings.VOUCHER_BRAND_NAME}/1.0 (booking voucher)"}
    async with httpx.AsyncClient(timeout=6.0, headers=headers) as client:

        async def _tile(tx: int, ty: int):
            url = settings.VOUCHER_MAP_TILE_URL.format(z=zoom, x=tx % n, y=ty)
            resp = await client.get(url)
            resp.raise_for_status()
            return tx, ty, resp.content

        coords = [(tx, ty) for ty in range(y0, y1 + 1) for tx in range(x0, x1 + 1)]
        tiles = await asyncio.gather(*[_tile(tx, ty) for tx, ty in coords])

    canvas = PILImage.new(
        "RGB", ((x1 - x0 + 1) * 256, (y1 - y0 + 1) * 256), (235, 235, 235)
    )
    for tx, ty, content in tiles:
        canvas.paste(
            PILImage.open(BytesIO(content)).convert("RGB"),
            ((tx - x0) * 256, (ty - y0) * 256),
        )
    crop_left, crop_top = int(left - x0 * 256), int(top - y0 * 256)
    crop = canvas.crop((crop_left, crop_top, crop_left + width, crop_top + height))

    draw = ImageDraw.Draw(crop)
    mx, my, r = width // 2, height // 2, 9
    draw.ellipse(
        [mx - r, my - 2 * r, mx + r, my],
        fill=(204, 0, 0),
        outline=(255, 255, 255),
        width=2,
    )
    draw.polygon([(mx - 6, my - 5), (mx + 6, my - 5), (mx, my + 7)], fill=(204, 0, 0))
    buf = BytesIO()
    crop.save(buf, format="PNG")
    return buf.getvalue()


def _rl_image(raw: bytes, max_w: float, max_h: float) -> RLImage | None:
    try:
        im = PILImage.open(BytesIO(raw)).convert("RGB")
        buf = BytesIO()
        im.save(buf, format="PNG")
        buf.seek(0)
        iw, ih = im.size
        scale = min(max_w / iw, max_h / ih)
        return RLImage(buf, width=iw * scale, height=ih * scale)
    except Exception:
        logger.warning("voucher: failed to embed image")
        return None


# ── small helpers ─────────────────────────────────────────────────────────────


def _board_label(board, lang: str) -> str | None:
    if board is None:
        return None
    value = board.value if hasattr(board, "value") else str(board)
    return _BOARD_LABELS.get(lang, _BOARD_LABELS["en"]).get(value)


def _payment_methods(ctx) -> str:
    if ctx.sanatorium is None:
        return ""
    methods = [str(m) for m in (ctx.sanatorium.payment_methods or []) if m]
    return ", ".join(methods)


def _guest_names(booking: Booking) -> list[str]:
    names: list[str] = []
    for entry in booking.guest_details or []:
        if isinstance(entry, dict):
            name = entry.get("full_name") or entry.get("name")
            if name:
                names.append(str(name))
    return names


def _localize_line(item: dict, labels, ctx) -> str:
    desc = str(item.get("description") or "")
    if desc.startswith("Extra bed"):
        return f"{labels['extra_bed']} × {item.get('qty', 1)}"
    if desc == "Room/program":
        return ctx.stay_name or labels["description"]
    return desc


def _cancellation_text(booking, sanatorium, lang, labels) -> str:
    if booking.refundable is False:
        return labels["non_refundable"]
    if booking.refundable is True:
        if booking.free_cancellation_days:
            return labels["free_cancellation_days"].format(
                days=booking.free_cancellation_days
            )
        return labels["free_cancellation"]
    if sanatorium is not None:
        text = pick_locale(sanatorium.cancellation_policy, lang)
        if text:
            return text
    return labels["see_policy"]


def _fmt_money(amount, currency: str) -> str:
    value = Decimal(str(amount)).quantize(Decimal("0.01"))
    # Non-breaking space so the currency never wraps away from the number.
    return f"{currency} {value:,.2f}"


def _esc(text) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
