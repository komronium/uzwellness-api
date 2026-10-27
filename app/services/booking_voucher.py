"""Render the booking voucher PDF (download + email attachment).

One A4 page, uz/ru/en. Read top to bottom it answers, in order, what a guest
asks at the door: is this booking valid (status banner), which booking
(reservation number), where (property, address, map link), when (dates and
times), what (room/package, meals, guests), how much and is it paid, what if
plans change (the cancellation terms the money logic actually applies), and
whom to call.

Everything printed is derived from the booking itself: the status from
`booking.status` (pending means unpaid — never print "confirmed" for it), the
cancellation wording from the same snapshot fields `cancellation_policy`
uses to compute refunds.

The property photo is embedded best-effort (downscaled JPEG) and skipped on any
failure, so the voucher always renders.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import httpx
from fastapi import HTTPException, status
from PIL import Image as PILImage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.storage import url_to_key
from app.core.utils import TASHKENT_TZ, pick_locale
from app.models.booking import Booking, BookingStatus, BookingType
from app.models.package import Package
from app.models.program import TreatmentProgram
from app.models.room import Room
from app.models.sanatorium import Sanatorium
from app.services.booking_invoice import build_invoice
from app.services.cancellation_policy import free_cancellation_deadline

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image as RLImage,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger("uzwellness.voucher")

_FONT = "VoucherSans"
_FONT_SEMI = "VoucherSans-SemiBold"
_FONT_BOLD = "VoucherSans-Bold"
_FONT_LOCK = threading.Lock()
_FONTS_READY = False

# Site palette (uzwellness.com's deep green), plus neutrals.
_BRAND = colors.HexColor("#2E5E4E")
_BRAND_SOFT = colors.HexColor("#EEF4F1")
_INK = colors.HexColor("#1B1F1D")
_MUTED = colors.HexColor("#5F6B66")
_LINE = colors.HexColor("#DCE3DF")

# Status banner: (text colour, background).
_STATUS_COLORS = {
    BookingStatus.CONFIRMED: (colors.HexColor("#14532D"), colors.HexColor("#DCFCE7")),
    BookingStatus.COMPLETED: (colors.HexColor("#14532D"), colors.HexColor("#DCFCE7")),
    BookingStatus.PENDING: (colors.HexColor("#7C4A03"), colors.HexColor("#FEF3C7")),
    BookingStatus.CANCELLED: (colors.HexColor("#7F1D1D"), colors.HexColor("#FEE2E2")),
}

_PAGE_W, _PAGE_H = A4
_MARGIN = 16 * mm
# The frame pads its content by 6pt per side; layout tables use the same width
# so their edges line up with the paragraphs.
_CONTENT_W = _PAGE_W - 2 * _MARGIN - 12

_ASSET_FONTS = Path(__file__).resolve().parents[1] / "assets" / "fonts"
# Bundled Noto Sans first so the PDF looks the same on every host; the system
# fonts are fallbacks for a checkout without the assets.
_FONT_CANDIDATES = [
    (
        str(_ASSET_FONTS / "NotoSans-Regular.ttf"),
        str(_ASSET_FONTS / "NotoSans-SemiBold.ttf"),
        str(_ASSET_FONTS / "NotoSans-Bold.ttf"),
    ),
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
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
            [
                (
                    settings.VOUCHER_FONT_PATH,
                    settings.VOUCHER_FONT_BOLD_PATH,
                    settings.VOUCHER_FONT_BOLD_PATH,
                )
            ]
            if settings.VOUCHER_FONT_PATH and settings.VOUCHER_FONT_BOLD_PATH
            else []
        )
        vera = os.path.join(bundled, "Vera.ttf"), os.path.join(bundled, "VeraBd.ttf")
        candidates = override + _FONT_CANDIDATES + [(vera[0], vera[1], vera[1])]
        for regular, semi, bold in candidates:
            if all(os.path.exists(p) for p in (regular, semi, bold)):
                pdfmetrics.registerFont(TTFont(_FONT, regular))
                pdfmetrics.registerFont(TTFont(_FONT_SEMI, semi))
                pdfmetrics.registerFont(TTFont(_FONT_BOLD, bold))
                pdfmetrics.registerFontFamily(_FONT, normal=_FONT, bold=_FONT_BOLD)
                _FONTS_READY = True
                return
        # reportlab ships Vera, so reaching here means the install is broken.
        # Still a server problem, not a bad request — say so in a sentence.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "The voucher PDF cannot be generated right now. "
                "Please try again later or ask us to email it to you."
            ),
        )


_LABELS: dict[str, dict[str, str]] = {
    "uz": {
        "title": "Bron vaucheri",
        "issued": "Berilgan sana: {date}",
        "status_confirmed": "Bron tasdiqlangan",
        "status_confirmed_note": (
            "To'lov qabul qilingan. Kelganingizda ushbu vaucherni ko'rsating."
        ),
        "status_completed": "Yashash yakunlangan",
        "status_completed_note": "Bizni tanlaganingiz uchun rahmat.",
        "status_pending": "To'lov kutilmoqda",
        "status_pending_note": (
            "Joy siz uchun band qilingan. Bron to'lovdan keyin tasdiqlanadi."
        ),
        "status_cancelled": "Bron bekor qilingan",
        "status_cancelled_note": "Bu bron endi amal qilmaydi.",
        "reservation_number": "Bron raqami",
        "booking_code": "Bron kodi",
        "check_in": "Kelish",
        "check_out": "Ketish",
        "nights": "Kecha",
        "guests": "Mehmon",
        "from_time": "{t} dan",
        "until_time": "{t} gacha",
        "details": "Bron tafsilotlari",
        "type": "Turi",
        "type_room": "Xona",
        "type_package": "Davolash paketi",
        "type_session": "Dastur",
        "name": "Nomi",
        "board": "Ovqatlanish",
        "rooms": "Xonalar",
        "guest_list": "Mehmonlar",
        "treatment": "Davolash",
        "passport": "pasport",
        "payment": "To'lov",
        "line_stay": "Yashash, {nights} kecha",
        "extra_bed": "Qo'shimcha o'rin × {n}",
        "transfer": "Transfer: {route}",
        "total": "Jami",
        "paid": "To'langan",
        "due": "To'lanishi kerak",
        "pay_how": (
            "Qanday to'lash mumkin: uzwellness.com saytida karta orqali yoki "
            "Uzum Bank ilovasida UzWellness xizmatini tanlab, bron raqamini kiriting."
        ),
        "pay_done": "To'lov UzWellness orqali qabul qilingan.",
        "extras_note": (
            "Obyektdagi qo'shimcha xizmatlar (agar bo'lsa) joyida alohida to'lanadi."
        ),
        "cancellation": "Bekor qilish shartlari",
        "non_refundable": (
            "Bu tarif qaytarilmaydi: bekor qilinsa, to'langan summa qaytarilmaydi."
        ),
        "free_until": "{date} gacha bepul bekor qilish mumkin.",
        "penalty_percent_after": "Undan keyin narxning {pct}% ushlab qolinadi.",
        "penalty_amount_after": "Undan keyin {amount} ushlab qolinadi.",
        "penalty_percent": "Bekor qilinsa, narxning {pct}% ushlab qolinadi.",
        "penalty_amount": "Bekor qilinsa, {amount} ushlab qolinadi.",
        "free": "Bepul bekor qilish mumkin: to'langan summa to'liq qaytariladi.",
        "arrival": "Joylashish",
        "checkin_from": "Kirish: {t} dan",
        "checkout_until": "Chiqish: {t} gacha",
        "pets_allowed": "Uy hayvonlari bilan kelish mumkin",
        "pets_not_allowed": "Uy hayvonlari bilan kelish mumkin emas",
        "property_rules": "Obyekt qoidalari",
        "contacts": "Aloqa",
        "property": "Obyekt",
        "support": "UzWellness yordam xizmati",
        "open_map": "Xaritada ochish",
        "footer": (
            "Ushbu vaucherni kelganingizda ko'rsating — telefonda yoki chop "
            "etilgan holda."
        ),
    },
    "ru": {
        "title": "Ваучер бронирования",
        "issued": "Выдан: {date}",
        "status_confirmed": "Бронирование подтверждено",
        "status_confirmed_note": "Оплата получена. Покажите этот ваучер при заезде.",
        "status_completed": "Проживание завершено",
        "status_completed_note": "Спасибо, что выбрали нас.",
        "status_pending": "Ожидает оплаты",
        "status_pending_note": (
            "Место забронировано за вами. Бронирование подтвердится после оплаты."
        ),
        "status_cancelled": "Бронирование отменено",
        "status_cancelled_note": "Это бронирование больше не действует.",
        "reservation_number": "Номер брони",
        "booking_code": "Код брони",
        "check_in": "Заезд",
        "check_out": "Выезд",
        "nights": "Ночей",
        "guests": "Гостей",
        "from_time": "с {t}",
        "until_time": "до {t}",
        "details": "Детали бронирования",
        "type": "Тип",
        "type_room": "Номер",
        "type_package": "Лечебный пакет",
        "type_session": "Программа",
        "name": "Название",
        "board": "Питание",
        "rooms": "Номеров",
        "guest_list": "Гости",
        "treatment": "Лечение",
        "passport": "паспорт",
        "payment": "Оплата",
        "line_stay": "Проживание, ночей: {nights}",
        "extra_bed": "Доп. кровать × {n}",
        "transfer": "Трансфер: {route}",
        "total": "Итого",
        "paid": "Оплачено",
        "due": "К оплате",
        "pay_how": (
            "Как оплатить: картой на сайте uzwellness.com или в приложении "
            "Uzum Bank — выберите сервис UzWellness и введите номер брони."
        ),
        "pay_done": "Оплата получена через UzWellness.",
        "extras_note": (
            "Дополнительные услуги на месте (если есть) оплачиваются отдельно."
        ),
        "cancellation": "Условия отмены",
        "non_refundable": (
            "Невозвратный тариф: при отмене оплаченная сумма не возвращается."
        ),
        "free_until": "Бесплатная отмена до {date}.",
        "penalty_percent_after": "После этого удерживается {pct}% стоимости.",
        "penalty_amount_after": "После этого удерживается {amount}.",
        "penalty_percent": "При отмене удерживается {pct}% стоимости.",
        "penalty_amount": "При отмене удерживается {amount}.",
        "free": "Бесплатная отмена: оплаченная сумма возвращается полностью.",
        "arrival": "Заселение",
        "checkin_from": "Заезд: с {t}",
        "checkout_until": "Выезд: до {t}",
        "pets_allowed": "Можно с домашними животными",
        "pets_not_allowed": "Без домашних животных",
        "property_rules": "Правила объекта",
        "contacts": "Контакты",
        "property": "Объект",
        "support": "Поддержка UzWellness",
        "open_map": "Открыть на карте",
        "footer": (
            "Покажите этот ваучер при заезде — на телефоне или в распечатанном виде."
        ),
    },
    "en": {
        "title": "Booking voucher",
        "issued": "Issued: {date}",
        "status_confirmed": "Booking confirmed",
        "status_confirmed_note": "Payment received. Show this voucher at check-in.",
        "status_completed": "Stay completed",
        "status_completed_note": "Thank you for staying with us.",
        "status_pending": "Awaiting payment",
        "status_pending_note": (
            "Your place is held. The booking is confirmed once it is paid."
        ),
        "status_cancelled": "Booking cancelled",
        "status_cancelled_note": "This booking is no longer valid.",
        "reservation_number": "Reservation number",
        "booking_code": "Booking code",
        "check_in": "Check-in",
        "check_out": "Check-out",
        "nights": "Nights",
        "guests": "Guests",
        "from_time": "from {t}",
        "until_time": "until {t}",
        "details": "Booking details",
        "type": "Type",
        "type_room": "Room",
        "type_package": "Treatment package",
        "type_session": "Program",
        "name": "Name",
        "board": "Meals",
        "rooms": "Rooms",
        "guest_list": "Guests",
        "treatment": "Treatment",
        "passport": "passport",
        "payment": "Payment",
        "line_stay": "Stay, {nights} night(s)",
        "extra_bed": "Extra bed × {n}",
        "transfer": "Transfer: {route}",
        "total": "Total",
        "paid": "Paid",
        "due": "Amount due",
        "pay_how": (
            "How to pay: by card on uzwellness.com, or in the Uzum Bank app — "
            "choose UzWellness and enter your reservation number."
        ),
        "pay_done": "Payment received via UzWellness.",
        "extras_note": (
            "Optional on-site services, if any, are paid separately at the property."
        ),
        "cancellation": "Cancellation policy",
        "non_refundable": (
            "Non-refundable rate: if cancelled, the amount paid is not returned."
        ),
        "free_until": "Free cancellation until {date}.",
        "penalty_percent_after": "After that, {pct}% of the price is withheld.",
        "penalty_amount_after": "After that, {amount} is withheld.",
        "penalty_percent": "If cancelled, {pct}% of the price is withheld.",
        "penalty_amount": "If cancelled, {amount} is withheld.",
        "free": "Free cancellation: the amount paid is refunded in full.",
        "arrival": "Arrival",
        "checkin_from": "Check-in: from {t}",
        "checkout_until": "Check-out: until {t}",
        "pets_allowed": "Pets allowed",
        "pets_not_allowed": "No pets",
        "property_rules": "Property rules",
        "contacts": "Contacts",
        "property": "Property",
        "support": "UzWellness support",
        "open_map": "Open in maps",
        "footer": "Show this voucher at check-in — on your phone or printed.",
    },
}

_BOARD_LABELS: dict[str, dict[str, str]] = {
    "uz": {
        "room_only": "ovqatsiz",
        "breakfast": "nonushta",
        "half_board": "yarim pansion (2 mahal)",
        "full_board": "to'liq pansion (3 mahal)",
        "all_inclusive": "hammasi kiritilgan",
    },
    "ru": {
        "room_only": "без питания",
        "breakfast": "завтрак",
        "half_board": "полупансион (2 приёма пищи)",
        "full_board": "полный пансион (3 приёма пищи)",
        "all_inclusive": "всё включено",
    },
    "en": {
        "room_only": "room only",
        "breakfast": "breakfast",
        "half_board": "half board (2 meals)",
        "full_board": "full board (3 meals)",
        "all_inclusive": "all inclusive",
    },
}

_MONTHS: dict[str, list[str]] = {
    "uz": [
        "yanvar",
        "fevral",
        "mart",
        "aprel",
        "may",
        "iyun",
        "iyul",
        "avgust",
        "sentyabr",
        "oktyabr",
        "noyabr",
        "dekabr",
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
}

_WEEKDAYS: dict[str, list[str]] = {
    "uz": [
        "dushanba",
        "seshanba",
        "chorshanba",
        "payshanba",
        "juma",
        "shanba",
        "yakshanba",
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
    "en": [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ],
}

# UZS reads as "11 900 000 so'm" / "11 900 000 сум"; English keeps the ISO code.
_UZS_SUFFIX = {"uz": "so'm", "ru": "сум"}


@dataclass(slots=True)
class _Ctx:
    lang: str
    labels: dict[str, str]
    sanatorium: Sanatorium | None
    sanatorium_name: str
    invoice: dict
    stay_name: str | None
    photo: bytes | None
    guests: list[tuple[str, str, str]] = field(default_factory=list)


async def build_voucher_pdf(
    db: AsyncSession, booking: Booking, locale: str = "en"
) -> bytes:
    """Render the booking voucher and return the PDF bytes."""
    _ensure_fonts()
    lang = locale if locale in _LABELS else "en"
    ctx = await _load_context(db, booking, lang)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"{ctx.labels['title']} {booking.reservation_number}",
        author=settings.VOUCHER_BRAND_NAME,
    )
    s = _styles()
    story: list = []
    story += _header(s, ctx)
    story += _status_banner(s, ctx, booking)
    story += _property_block(s, ctx)
    story += _stay_strip(s, ctx, booking)
    story += _details(s, ctx, booking)
    story += _payment(s, ctx, booking)
    story += _policies(s, ctx, booking)
    story += _contacts(s, ctx)
    doc.build(story)
    return buffer.getvalue()


# ── styles ────────────────────────────────────────────────────────────────────


def _styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle(
        "v", fontName=_FONT, fontSize=9.5, leading=13.5, textColor=_INK
    )

    def style(name: str, **kw) -> ParagraphStyle:
        return ParagraphStyle(name, parent=base, **kw)

    return {
        "base": base,
        "muted": style("muted", fontSize=8.5, leading=12, textColor=_MUTED),
        "small": style("small", fontSize=8, leading=11, textColor=_MUTED),
        "brand": style(
            "brand", fontName=_FONT_BOLD, fontSize=17, leading=20, textColor=_BRAND
        ),
        "title": style(
            "title", fontName=_FONT_SEMI, fontSize=11, leading=14, alignment=TA_RIGHT
        ),
        "issued": style(
            "issued", fontSize=8, leading=11, textColor=_MUTED, alignment=TA_RIGHT
        ),
        "status": style("status", fontName=_FONT_BOLD, fontSize=12.5, leading=16),
        "status_note": style("status_note", fontSize=9, leading=12.5),
        "label": style("label", fontSize=7.5, leading=10, textColor=_MUTED),
        "number": style(
            "number", fontName=_FONT_BOLD, fontSize=15, leading=19, textColor=_BRAND
        ),
        "code": style(
            "code", fontName=_FONT_SEMI, fontSize=11, leading=19, alignment=TA_RIGHT
        ),
        "property": style("property", fontName=_FONT_BOLD, fontSize=13, leading=16.5),
        "link": style(
            "link", fontName=_FONT_SEMI, fontSize=8.5, leading=12, textColor=_BRAND
        ),
        "strip_value": style(
            "strip_value", fontName=_FONT_BOLD, fontSize=12, leading=15
        ),
        "strip_sub": style("strip_sub", fontSize=8, leading=10.5, textColor=_MUTED),
        "h": style(
            "h",
            fontName=_FONT_SEMI,
            fontSize=10.5,
            leading=14,
            textColor=_BRAND,
            spaceBefore=11,
            spaceAfter=4,
        ),
        "key": style("key", fontSize=9, leading=13, textColor=_MUTED),
        "value": style("value", fontName=_FONT_SEMI, fontSize=9.5, leading=13),
        "right": style("right", alignment=TA_RIGHT),
        "total_label": style(
            "total_label", fontName=_FONT_BOLD, fontSize=11.5, leading=15
        ),
        "total_value": style(
            "total_value",
            fontName=_FONT_BOLD,
            fontSize=13,
            leading=16,
            alignment=TA_RIGHT,
            textColor=_BRAND,
        ),
    }


# ── sections ──────────────────────────────────────────────────────────────────


def _header(s, ctx: _Ctx) -> list:
    issued = ctx.labels["issued"].format(
        date=_fmt_date(datetime.now(UTC).astimezone(TASHKENT_TZ).date(), ctx.lang)
    )
    table = Table(
        [
            [
                Paragraph(_esc(settings.VOUCHER_BRAND_NAME), s["brand"]),
                [
                    Paragraph(ctx.labels["title"], s["title"]),
                    Paragraph(issued, s["issued"]),
                ],
            ]
        ],
        colWidths=[_CONTENT_W * 0.5, _CONTENT_W * 0.5],
    )
    table.setStyle(_plain([("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
    return [table, Spacer(1, 5), _rule(_BRAND, 1.2), Spacer(1, 9)]


def _status_banner(s, ctx: _Ctx, booking: Booking) -> list:
    key = _status_key(booking)
    fg, bg = _STATUS_COLORS.get(booking.status, _STATUS_COLORS[BookingStatus.PENDING])
    title = ParagraphStyle("st", parent=s["status"], textColor=fg)
    note = ParagraphStyle("stn", parent=s["status_note"], textColor=fg)
    number = [
        Paragraph(ctx.labels["reservation_number"], s["label"]),
        Paragraph(_group_digits(booking.reservation_number), s["number"]),
    ]
    code = [
        Paragraph(
            ctx.labels["booking_code"],
            ParagraphStyle("cl", parent=s["label"], alignment=TA_RIGHT),
        ),
        Paragraph(_esc(booking.code), s["code"]),
    ]
    banner = Table(
        [
            [
                [
                    Paragraph(ctx.labels[f"status_{key}"], title),
                    Paragraph(ctx.labels[f"status_{key}_note"], note),
                ]
            ]
        ],
        colWidths=[_CONTENT_W],
    )
    banner.setStyle(
        _plain(
            [
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("ROUNDEDCORNERS", [6, 6, 6, 6]),
            ]
        )
    )
    ids = Table([[number, code]], colWidths=[_CONTENT_W * 0.6, _CONTENT_W * 0.4])
    ids.setStyle(_plain([("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
    return [banner, Spacer(1, 10), ids, Spacer(1, 10)]


def _property_block(s, ctx: _Ctx) -> list:
    sanatorium = ctx.sanatorium
    lines: list = [Paragraph(_esc(ctx.sanatorium_name), s["property"])]
    if sanatorium is not None:
        address = pick_locale(sanatorium.address, ctx.lang)
        if address:
            lines.append(Paragraph(_esc(address), s["muted"]))
        phones = [str(p) for p in (sanatorium.phones or []) if p]
        if phones:
            lines.append(Paragraph(_esc(", ".join(phones)), s["muted"]))
        if sanatorium.lat is not None and sanatorium.lng is not None:
            url = f"https://www.google.com/maps?q={sanatorium.lat},{sanatorium.lng}"
            lines.append(Spacer(1, 2))
            lines.append(
                Paragraph(
                    f'<link href="{url}">{ctx.labels["open_map"]}</link>', s["link"]
                )
            )

    photo = _rl_image(ctx.photo, 46 * mm, 30 * mm) if ctx.photo else None
    if photo is None:
        return [*lines, Spacer(1, 10)]
    table = Table([[photo, lines]], colWidths=[50 * mm, _CONTENT_W - 50 * mm])
    table.setStyle(_plain([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    return [table, Spacer(1, 10)]


def _stay_strip(s, ctx: _Ctx, booking: Booking) -> list:
    labels = ctx.labels
    ci_time = ctx.sanatorium.check_in_time if ctx.sanatorium else None
    co_time = ctx.sanatorium.check_out_time if ctx.sanatorium else None

    def date_cell(label: str, value: date, t: time | None, template: str) -> list:
        sub = _WEEKDAYS[ctx.lang][value.weekday()]
        if t is not None:
            sub += " · " + template.format(t=t.strftime("%H:%M"))
        return [
            Paragraph(label, s["label"]),
            Paragraph(_fmt_date(value, ctx.lang), s["strip_value"]),
            Paragraph(_esc(sub), s["strip_sub"]),
        ]

    def count_cell(label: str, value: int) -> list:
        return [Paragraph(label, s["label"]), Paragraph(str(value), s["strip_value"])]

    row = [
        date_cell(labels["check_in"], booking.check_in, ci_time, labels["from_time"]),
        date_cell(
            labels["check_out"], booking.check_out, co_time, labels["until_time"]
        ),
        count_cell(labels["nights"], ctx.invoice["nights"]),
        count_cell(labels["guests"], booking.guests),
    ]
    widths = [
        _CONTENT_W * 0.33,
        _CONTENT_W * 0.33,
        _CONTENT_W * 0.17,
        _CONTENT_W * 0.17,
    ]
    strip = Table([row], colWidths=widths)
    strip.setStyle(
        _plain(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _BRAND_SOFT),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("LINEAFTER", (0, 0), (-2, -1), 0.6, _LINE),
                ("ROUNDEDCORNERS", [6, 6, 6, 6]),
            ]
        )
    )
    return [strip]


def _details(s, ctx: _Ctx, booking: Booking) -> list:
    labels = ctx.labels
    # (label, value as Paragraph markup — escape plain text on the way in)
    rows: list[tuple[str, str]] = []
    type_key = {
        BookingType.ROOM: "type_room",
        BookingType.PACKAGE: "type_package",
        BookingType.SESSION: "type_session",
    }.get(booking.booking_type)
    if type_key:
        rows.append((labels["type"], _esc(labels[type_key])))
    if ctx.stay_name:
        rows.append((labels["name"], _esc(ctx.stay_name)))
    board = _board_label(booking.board, ctx.lang)
    if board:
        rows.append((labels["board"], _esc(board)))
    if booking.booking_type != BookingType.SESSION and booking.rooms_count:
        rows.append((labels["rooms"], str(booking.rooms_count)))

    if ctx.guests:
        lines = []
        for name, passport, treatment in ctx.guests:
            line = f"<font name='{_FONT_SEMI}'>{_esc(name)}</font>"
            if passport:
                line += f" · {labels['passport']} {_esc(passport)}"
            if treatment:
                line += f"<br/><font color='#5F6B66' size='8.5'>{labels['treatment']}: {_esc(treatment)}</font>"
            lines.append(line)
        rows.append((labels["guest_list"], "<br/>".join(lines)))

    data = [[Paragraph(_esc(k), s["key"]), Paragraph(v, s["value"])] for k, v in rows]
    table = Table(data, colWidths=[38 * mm, _CONTENT_W - 38 * mm])
    table.setStyle(
        _plain(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -2), 0.5, _LINE),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return [Paragraph(labels["details"], s["h"]), table]


def _payment(s, ctx: _Ctx, booking: Booking) -> list:
    labels = ctx.labels
    currency = ctx.invoice["currency"]
    data = []
    for item in ctx.invoice["line_items"]:
        data.append(
            [
                Paragraph(_esc(_line_label(item, ctx, booking)), s["base"]),
                Paragraph(_fmt_money(item["amount"], currency, ctx.lang), s["right"]),
            ]
        )
    lines = Table(data, colWidths=[_CONTENT_W * 0.65, _CONTENT_W * 0.35])
    lines.setStyle(
        _plain(
            [
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, _LINE),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )

    paid = booking.status in (BookingStatus.CONFIRMED, BookingStatus.COMPLETED)
    total_label = labels["paid"] if paid else labels["total"]
    total = Table(
        [
            [
                Paragraph(total_label, s["total_label"]),
                Paragraph(
                    _fmt_money(ctx.invoice["total"], currency, ctx.lang),
                    s["total_value"],
                ),
            ]
        ],
        colWidths=[_CONTENT_W * 0.5, _CONTENT_W * 0.5],
    )
    total.setStyle(
        _plain(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _BRAND_SOFT),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("ROUNDEDCORNERS", [6, 6, 6, 6]),
            ]
        )
    )
    notes: list[str] = []
    if paid:
        notes.append(labels["pay_done"])
    elif booking.status == BookingStatus.PENDING:
        notes.append(labels["pay_how"])
    notes.append(labels["extras_note"])
    out = [
        Paragraph(labels["payment"], s["h"]),
        lines,
        Spacer(1, 6),
        total,
        Spacer(1, 5),
    ]
    out += [Paragraph(_esc(n), s["muted"]) for n in notes]
    return [KeepTogether(out)]


def _policies(s, ctx: _Ctx, booking: Booking) -> list:
    labels = ctx.labels
    left = [Paragraph(labels["cancellation"], s["h"])]
    for line in _cancellation_lines(booking, ctx):
        left.append(Paragraph(_esc(line), s["base"]))

    right = [Paragraph(labels["arrival"], s["h"])]
    sanatorium = ctx.sanatorium
    arrival: list[str] = []
    if sanatorium is not None:
        if sanatorium.check_in_time is not None:
            arrival.append(
                labels["checkin_from"].format(
                    t=sanatorium.check_in_time.strftime("%H:%M")
                )
            )
        if sanatorium.check_out_time is not None:
            arrival.append(
                labels["checkout_until"].format(
                    t=sanatorium.check_out_time.strftime("%H:%M")
                )
            )
        if sanatorium.pets_allowed is True:
            arrival.append(labels["pets_allowed"])
        elif sanatorium.pets_allowed is False:
            arrival.append(labels["pets_not_allowed"])
    for line in arrival:
        right.append(Paragraph(_esc(line), s["base"]))
    if len(right) == 1:
        right = []

    table = Table([[left, right]], colWidths=[_CONTENT_W * 0.55, _CONTENT_W * 0.45])
    table.setStyle(
        _plain(
            [("VALIGN", (0, 0), (-1, -1), "TOP"), ("RIGHTPADDING", (0, 0), (0, 0), 14)]
        )
    )
    # A heading's spaceBefore is dropped inside a table cell; space it here.
    out: list = [Spacer(1, 6), table]
    rules = pick_locale(sanatorium.house_rules, ctx.lang) if sanatorium else ""
    if rules:
        out.append(Paragraph(labels["property_rules"], s["h"]))
        out.append(Paragraph(_esc(rules), s["muted"]))
    return [KeepTogether(out)]


def _contacts(s, ctx: _Ctx) -> list:
    labels = ctx.labels
    sanatorium = ctx.sanatorium
    prop: list[str] = []
    if sanatorium is not None:
        prop += [str(p) for p in (sanatorium.phones or []) if p]
        if sanatorium.customer_support_email:
            prop.append(sanatorium.customer_support_email)
    support = [settings.SUPPORT_EMAIL] + (
        [settings.SUPPORT_PHONE] if settings.SUPPORT_PHONE else []
    )

    cells = []
    if prop:
        cells.append(
            [
                Paragraph(labels["property"], s["label"]),
                Paragraph(_esc(" · ".join(prop)), s["base"]),
            ]
        )
    cells.append(
        [
            Paragraph(labels["support"], s["label"]),
            Paragraph(_esc(" · ".join(support)), s["base"]),
        ]
    )
    table = Table([cells], colWidths=[_CONTENT_W / len(cells)] * len(cells))
    table.setStyle(_plain([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return [
        KeepTogether(
            [
                Spacer(1, 12),
                _rule(_LINE, 0.8),
                Spacer(1, 6),
                Paragraph(
                    labels["contacts"],
                    ParagraphStyle("ch", parent=s["h"], spaceBefore=0),
                ),
                table,
                Spacer(1, 8),
                Paragraph(_esc(labels["footer"]), s["small"]),
            ]
        )
    ]


# ── data loading ──────────────────────────────────────────────────────────────


async def _load_context(db: AsyncSession, booking: Booking, lang: str) -> _Ctx:
    invoice = await build_invoice(db, booking)
    sanatorium = await _load_sanatorium(db, booking)
    # The invoice resolves the name in one locale; the voucher wants the reader's.
    name = (
        pick_locale(sanatorium.name, lang) if sanatorium is not None else ""
    ) or invoice["sanatorium_name"]
    return _Ctx(
        lang=lang,
        labels=_LABELS[lang],
        sanatorium=sanatorium,
        sanatorium_name=name,
        invoice=invoice,
        stay_name=await _stay_name(db, booking, lang),
        photo=await _fetch_photo(sanatorium),
        guests=_guest_rows(booking, invoice),
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


async def _stay_name(db: AsyncSession, booking: Booking, lang: str) -> str | None:
    # A package booking also carries the package's room_id, so the package
    # title wins: it is what the guest bought.
    name: dict | None = None
    if booking.package_id is not None:
        name = await db.scalar(
            select(Package.title).where(Package.id == booking.package_id)
        )
    elif booking.room_id is not None:
        name = await db.scalar(select(Room.name).where(Room.id == booking.room_id))
    elif booking.program_id is not None:
        name = await db.scalar(
            select(TreatmentProgram.name).where(
                TreatmentProgram.id == booking.program_id
            )
        )
    return (pick_locale(name, lang) or None) if name else None


def _guest_rows(booking: Booking, invoice: dict) -> list[tuple[str, str, str]]:
    """(name, passport, treatment) per guest; empty parts are left out."""
    treatments = _guest_treatments(booking)
    rows: list[tuple[str, str, str]] = []
    for i, gd in enumerate(booking.guest_details or []):
        if not isinstance(gd, dict):
            continue
        name = (gd.get("full_name") or "").strip()
        if not name:
            continue
        treatment = treatments[i] if i < len(treatments) else ""
        rows.append((name, (gd.get("passport") or "").strip(), treatment))
    if not rows and invoice["customer_name"]:
        rows.append((invoice["customer_name"], "", treatments[0] if treatments else ""))
    return rows


def _guest_treatments(booking: Booking) -> list[str]:
    """Per-guest treatment title from the offer snapshot, in guest order."""
    inclusions = (booking.offer_snapshot or {}).get("inclusions") or []

    def _key(entry: dict):
        guest = entry.get("guest") or {}
        return (entry.get("room_index", 0), guest.get("guest_index", 0))

    out: list[str] = []
    for entry in sorted(inclusions, key=_key):
        title = ""
        for item in entry.get("items") or []:
            if item.get("type") in ("treatment", "special_package"):
                title = (item.get("title") or "").strip()
                if title:
                    break
        out.append(title)
    return out


async def _fetch_photo(sanatorium: Sanatorium | None) -> bytes | None:
    if sanatorium is None or not sanatorium.images:
        return None
    images = sanatorium.images
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


def _rl_image(raw: bytes, max_w: float, max_h: float) -> RLImage | None:
    try:
        jpeg, width, height = _print_jpeg(raw, max_w, max_h)
        return RLImage(BytesIO(jpeg), width=width, height=height)
    except Exception:
        logger.warning("voucher: failed to embed image")
        return None


def _print_jpeg(raw: bytes, max_w: float, max_h: float) -> tuple[bytes, float, float]:
    """Photo as a JPEG sized for print, plus its size in points.

    A full-resolution upload made the voucher ~1.5 MB — heavy for an email
    attachment. ~200 dpi at the printed size is plenty for paper and screens.
    """
    im = PILImage.open(BytesIO(raw)).convert("RGB")
    iw, ih = im.size
    scale = min(max_w / iw, max_h / ih)
    target_px = (
        max(1, int(iw * scale / 72 * 200)),
        max(1, int(ih * scale / 72 * 200)),
    )
    if target_px[0] < iw:
        im = im.resize(target_px, PILImage.Resampling.LANCZOS)
    buf = BytesIO()
    im.save(buf, format="JPEG", quality=82, optimize=True)
    return buf.getvalue(), iw * scale, ih * scale


# ── small helpers ─────────────────────────────────────────────────────────────


def _status_key(booking: Booking) -> str:
    return {
        BookingStatus.CONFIRMED: "confirmed",
        BookingStatus.COMPLETED: "completed",
        BookingStatus.CANCELLED: "cancelled",
    }.get(booking.status, "pending")


def _cancellation_lines(booking: Booking, ctx: _Ctx) -> list[str]:
    """The terms `cancellation_policy.refund_for` will actually apply."""
    labels = ctx.labels
    if booking.refundable is False:
        return [labels["non_refundable"]]
    currency = ctx.invoice["currency"]
    penalty = None
    if booking.cancellation_penalty_amount:
        penalty = (
            "amount",
            _fmt_money(booking.cancellation_penalty_amount, currency, ctx.lang),
        )
    elif booking.cancellation_penalty_percent:
        penalty = ("percent", _fmt_percent(booking.cancellation_penalty_percent))

    deadline = free_cancellation_deadline(booking)
    if penalty is None:
        if deadline is not None:
            return [labels["free_until"].format(date=_fmt_date(deadline, ctx.lang))]
        return [labels["free"]]
    kind, value = penalty
    if deadline is None:
        key = "penalty_amount" if kind == "amount" else "penalty_percent"
        return [labels[key].format(amount=value, pct=value)]
    key = "penalty_amount_after" if kind == "amount" else "penalty_percent_after"
    return [
        labels["free_until"].format(date=_fmt_date(deadline, ctx.lang)),
        labels[key].format(amount=value, pct=value),
    ]


def _line_label(item: dict, ctx: _Ctx, booking: Booking) -> str:
    labels = ctx.labels
    desc = str(item.get("description") or "")
    if desc == "Room/program":
        if booking.booking_type == BookingType.ROOM or not ctx.stay_name:
            return labels["line_stay"].format(nights=ctx.invoice["nights"])
        return ctx.stay_name
    if desc.startswith("Extra bed"):
        return labels["extra_bed"].format(n=item.get("qty", 1))
    if desc.startswith("Transfer ("):
        return labels["transfer"].format(route=desc[len("Transfer (") : -1])
    return desc


def _board_label(board, lang: str) -> str | None:
    if board is None:
        return None
    value = board.value if hasattr(board, "value") else str(board)
    return _BOARD_LABELS[lang].get(value)


def _fmt_date(value: date, lang: str) -> str:
    month = _MONTHS[lang][value.month - 1]
    if lang == "uz":
        return f"{value.day}-{month}, {value.year}"
    return f"{value.day} {month} {value.year}"


def _fmt_money(amount, currency: str, lang: str) -> str:
    value = Decimal(str(amount))
    if currency == "UZS":
        whole = f"{value.quantize(Decimal('1')):,}"
        if lang in _UZS_SUFFIX:
            # Narrow no-break spaces: digits group the local way and never wrap.
            return whole.replace(",", " ") + " " + _UZS_SUFFIX[lang]
        return f"UZS {whole}"
    symbol = {"USD": "$", "EUR": "€"}.get(currency)
    text = f"{value.quantize(Decimal('0.01')):,.2f}"
    return f"{symbol}{text}" if symbol else f"{currency} {text}"


def _fmt_percent(value) -> str:
    return f"{Decimal(str(value)).normalize():f}"


def _group_digits(number: str) -> str:
    """2610053172617351 -> 2610 0531 7261 7351, easy to read out and type."""
    digits = str(number)
    return " ".join(digits[i : i + 4] for i in range(0, len(digits), 4))


def _rule(color, thickness: float) -> Table:
    line = Table([[""]], colWidths=[_CONTENT_W], rowHeights=[0])
    line.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, -1), thickness, color)]))
    return line


def _plain(extra: list) -> TableStyle:
    """No padding unless asked — layout tables, not data grids."""
    return TableStyle(
        [
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            *extra,
        ]
    )


def _esc(text) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
