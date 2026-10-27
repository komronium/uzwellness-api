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
        "type": "Turi",
        "type_room": "Xona",
        "type_package": "Davolash paketi",
        "type_session": "Dastur",
        "board": "Ovqatlanish",
        "rooms": "Xonalar",
        "guest_list": "Mehmonlar",
        "treatment": "Davolash",
        "guests_treatment": "Mehmonlar va davolash",
        "col_guest": "Mehmon",
        "col_treatment": "Davolash dasturi",
        "adult": "Katta yoshli",
        "child_age": "Bola, {age} yosh",
        "child": "Bola",
        "stay_only": "Faqat yashash, davolashsiz",
        "passport": "pasport",
        "payment": "To'lov",
        "line_stay": "Yashash, {nights} kecha",
        "extra_bed": "Qo'shimcha o'rin × {n}",
        "transfer": "Transfer: {route}",
        "total": "Jami",
        "paid": "To'langan",
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
        "contacts": "Aloqa",
        "property": "Obyekt",
        "support": "UzWellness yordam xizmati",
        "open_map": "Xaritada ochish",
    },
    "ru": {
        "title": "Ваучер бронирования",
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
        "type": "Тип",
        "type_room": "Номер",
        "type_package": "Лечебный пакет",
        "type_session": "Программа",
        "board": "Питание",
        "rooms": "Номеров",
        "guest_list": "Гости",
        "treatment": "Лечение",
        "guests_treatment": "Гости и лечение",
        "col_guest": "Гость",
        "col_treatment": "Лечебная программа",
        "adult": "Взрослый",
        "child_age": "Ребёнок, {age} лет",
        "child": "Ребёнок",
        "stay_only": "Только проживание, без лечения",
        "passport": "паспорт",
        "payment": "Оплата",
        "line_stay": "Проживание, ночей: {nights}",
        "extra_bed": "Доп. кровать × {n}",
        "transfer": "Трансфер: {route}",
        "total": "Итого",
        "paid": "Оплачено",
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
        "contacts": "Контакты",
        "property": "Объект",
        "support": "Поддержка UzWellness",
        "open_map": "Открыть на карте",
    },
    "en": {
        "title": "Booking voucher",
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
        "type": "Type",
        "type_room": "Room",
        "type_package": "Treatment package",
        "type_session": "Program",
        "board": "Meals",
        "rooms": "Rooms",
        "guest_list": "Guests",
        "treatment": "Treatment",
        "guests_treatment": "Guests and treatment",
        "col_guest": "Guest",
        "col_treatment": "Treatment program",
        "adult": "Adult",
        "child_age": "Child, {age}",
        "child": "Child",
        "stay_only": "Stay only, no treatment",
        "passport": "passport",
        "payment": "Payment",
        "line_stay": "Stay, {nights} night(s)",
        "extra_bed": "Extra bed × {n}",
        "transfer": "Transfer: {route}",
        "total": "Total",
        "paid": "Paid",
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
        "contacts": "Contacts",
        "property": "Property",
        "support": "UzWellness support",
        "open_map": "Open in maps",
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
class _Guest:
    name: str
    passport: str = ""
    child_age: int | None = None
    is_child: bool = False
    treatment: str = ""
    treatment_detail: str = ""


@dataclass(slots=True)
class _Ctx:
    lang: str
    labels: dict[str, str]
    sanatorium: Sanatorium | None
    sanatorium_name: str
    invoice: dict
    stay_name: str | None
    photo: bytes | None
    guests: list[_Guest] = field(default_factory=list)


async def build_voucher_pdf(
    db: AsyncSession, booking: Booking, locale: str = "en"
) -> bytes:
    """Render the booking voucher (always one A4 page) and return the PDF bytes."""
    _ensure_fonts()
    lang = locale if locale in _LABELS else "en"
    ctx = await _load_context(db, booking, lang)

    return _render_one_page(ctx, booking)[0]


def _render_one_page(ctx: _Ctx, booking: Booking) -> tuple[bytes, int]:
    """A voucher is one sheet of paper.

    A large family with long program descriptions can overflow the roomy
    layout; re-render it compact (no photo, tighter type, program details
    trimmed) rather than spill onto a second page.
    """
    pdf, pages = _render(ctx, booking, compact=False)
    if pages > 1:
        pdf, pages = _render(ctx, booking, compact=True)
        if pages > 1:
            logger.warning(
                "voucher %s still spans %d pages in compact mode",
                booking.reservation_number,
                pages,
            )
    return pdf, pages


def _render(ctx: _Ctx, booking: Booking, *, compact: bool) -> tuple[bytes, int]:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"{ctx.labels['title']} {booking.reservation_number}",
        author=settings.VOUCHER_BRAND_NAME,
    )
    s = _styles(compact)
    story: list = []
    story += _header(s, ctx, booking)
    story += _status_banner(s, ctx, booking)
    story += _property_block(s, ctx, compact)
    story += _stay_card(s, ctx, booking)
    story += _guests(s, ctx, compact)
    story += _payment(s, ctx, booking)
    story += _footer_grid(s, ctx, booking)
    doc.build(story)
    return buffer.getvalue(), doc.page


# ── styles ────────────────────────────────────────────────────────────────────


def _styles(compact: bool = False) -> dict[str, ParagraphStyle]:
    k = 0.92 if compact else 1.0  # type scale
    base = ParagraphStyle(
        "v", fontName=_FONT, fontSize=9.5 * k, leading=13 * k, textColor=_INK
    )

    def style(name: str, size: float, leading: float, **kw) -> ParagraphStyle:
        return ParagraphStyle(
            name, parent=base, fontSize=size * k, leading=leading * k, **kw
        )

    return {
        "base": base,
        "muted": style("muted", 8.5, 11.5, textColor=_MUTED),
        "brand": style("brand", 18, 21, fontName=_FONT_BOLD, textColor=_BRAND),
        "doc": style("doc", 8.5, 11, textColor=_MUTED),
        "label": style("label", 7.5, 9.5, textColor=_MUTED),
        "label_r": style("label_r", 7.5, 9.5, textColor=_MUTED, alignment=TA_RIGHT),
        "number": style(
            "number", 16, 19, fontName=_FONT_BOLD, textColor=_BRAND, alignment=TA_RIGHT
        ),
        "code": style("code", 8, 10.5, textColor=_MUTED, alignment=TA_RIGHT),
        "status": style("status", 10, 13.5),
        "property": style("property", 13, 16, fontName=_FONT_BOLD),
        "link": style("link", 8.5, 11.5, fontName=_FONT_SEMI, textColor=_BRAND),
        "strip_value": style("strip_value", 12, 15, fontName=_FONT_BOLD),
        "strip_sub": style("strip_sub", 8, 10.5, textColor=_MUTED),
        "summary": style("summary", 9, 12),
        "h": style(
            "h",
            10,
            13,
            fontName=_FONT_SEMI,
            textColor=_BRAND,
            spaceBefore=9 * k,
            spaceAfter=3 * k,
        ),
        "h_cell": style("h_cell", 10, 13, fontName=_FONT_SEMI, textColor=_BRAND),
        "value": style("value", 9.5, 12.5, fontName=_FONT_SEMI),
        "right": style("right", 9.5, 13, alignment=TA_RIGHT),
        "total_label": style("total_label", 11, 14, fontName=_FONT_BOLD),
        "total_value": style(
            "total_value",
            13,
            16,
            fontName=_FONT_BOLD,
            alignment=TA_RIGHT,
            textColor=_BRAND,
        ),
        "cell": style("cell", 8.5, 11.5),
    }


# ── sections ──────────────────────────────────────────────────────────────────


def _header(s, ctx: _Ctx, booking: Booking) -> list:
    """Brand on the left; the number the guest quotes on the right."""
    issued = _fmt_date(datetime.now(UTC).astimezone(TASHKENT_TZ).date(), ctx.lang)
    left = [
        Paragraph(_esc(settings.VOUCHER_BRAND_NAME), s["brand"]),
        Paragraph(f"{ctx.labels['title']} · {_esc(issued)}", s["doc"]),
    ]
    right = [
        Paragraph(ctx.labels["reservation_number"], s["label_r"]),
        Paragraph(_group_digits(booking.reservation_number), s["number"]),
        Paragraph(f"{ctx.labels['booking_code']}: {_esc(booking.code)}", s["code"]),
    ]
    table = Table([[left, right]], colWidths=[_CONTENT_W * 0.45, _CONTENT_W * 0.55])
    table.setStyle(_plain([("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
    return [table, Spacer(1, 6), _rule(_BRAND, 1.2), Spacer(1, 8)]


def _status_banner(s, ctx: _Ctx, booking: Booking) -> list:
    key = _status_key(booking)
    fg, bg = _STATUS_COLORS.get(booking.status, _STATUS_COLORS[BookingStatus.PENDING])
    text = ParagraphStyle("st", parent=s["status"], textColor=fg)
    banner = Table(
        [
            [
                Paragraph(
                    f"<font name='{_FONT_BOLD}'>{ctx.labels[f'status_{key}']}</font>"
                    f" — {ctx.labels[f'status_{key}_note']}",
                    text,
                )
            ]
        ],
        colWidths=[_CONTENT_W],
    )
    banner.setStyle(
        _plain(
            [
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("LEFTPADDING", (0, 0), (-1, -1), 11),
                ("RIGHTPADDING", (0, 0), (-1, -1), 11),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("ROUNDEDCORNERS", [6, 6, 6, 6]),
            ]
        )
    )
    return [banner, Spacer(1, 10)]


def _property_block(s, ctx: _Ctx, compact: bool) -> list:
    sanatorium = ctx.sanatorium
    lines: list = [Paragraph(_esc(ctx.sanatorium_name), s["property"])]
    if sanatorium is not None:
        address = pick_locale(sanatorium.address, ctx.lang)
        phones = [str(p) for p in (sanatorium.phones or []) if p]
        info = " · ".join([x for x in [address, ", ".join(phones)] if x])
        if info:
            lines.append(Paragraph(_esc(info), s["muted"]))
        if sanatorium.lat is not None and sanatorium.lng is not None:
            url = f"https://www.google.com/maps?q={sanatorium.lat},{sanatorium.lng}"
            lines.append(
                Paragraph(
                    f'<link href="{url}">{ctx.labels["open_map"]}</link>', s["link"]
                )
            )

    photo = None if compact or not ctx.photo else _rl_image(ctx.photo, 34 * mm, 22 * mm)
    if photo is None:
        return [*lines, Spacer(1, 8)]
    table = Table([[photo, lines]], colWidths=[38 * mm, _CONTENT_W - 38 * mm])
    table.setStyle(_plain([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    return [table, Spacer(1, 8)]


def _stay_card(s, ctx: _Ctx, booking: Booking) -> list:
    """Dates and counts, with what was booked as one line underneath."""
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
    data = [row]
    summary = _booking_summary(ctx, booking)
    if summary:
        data.append([Paragraph(summary, s["summary"]), "", "", ""])
    widths = [
        _CONTENT_W * 0.34,
        _CONTENT_W * 0.34,
        _CONTENT_W * 0.16,
        _CONTENT_W * 0.16,
    ]
    card = Table(data, colWidths=widths)
    style = [
        ("BACKGROUND", (0, 0), (-1, -1), _BRAND_SOFT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 11),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("LINEAFTER", (0, 0), (-2, 0), 0.6, _LINE),
        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
    ]
    if summary:
        style += [
            ("SPAN", (0, 1), (-1, 1)),
            ("LINEABOVE", (0, 1), (-1, 1), 0.6, _LINE),
            ("TOPPADDING", (0, 1), (-1, 1), 6),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 7),
        ]
    card.setStyle(_plain(style))
    return [card]


def _booking_summary(ctx: _Ctx, booking: Booking) -> str:
    """'Room: Family Triple · 1 room · full board' as Paragraph markup."""
    labels = ctx.labels
    type_key = {
        BookingType.ROOM: "type_room",
        BookingType.PACKAGE: "type_package",
        BookingType.SESSION: "type_session",
    }.get(booking.booking_type)
    parts: list[str] = []
    if ctx.stay_name:
        prefix = f"{labels[type_key]}: " if type_key else ""
        parts.append(f"<font name='{_FONT_SEMI}'>{_esc(prefix + ctx.stay_name)}</font>")
    if booking.booking_type != BookingType.SESSION and booking.rooms_count:
        parts.append(_esc(f"{labels['rooms']}: {booking.rooms_count}"))
    board = _board_label(booking.board, ctx.lang)
    if board:
        parts.append(_esc(f"{labels['board']}: {board}"))
    return "  ·  ".join(parts)


def _has_treatments(ctx: _Ctx) -> bool:
    return any(g.treatment for g in ctx.guests)


def _guests(s, ctx: _Ctx, compact: bool) -> list:
    """One row per guest — and, when booked, exactly which program they get."""
    if not ctx.guests:
        return []
    labels = ctx.labels
    with_treatment = _has_treatments(ctx)
    rows = []
    for i, guest in enumerate(ctx.guests, start=1):
        meta = [_guest_kind(guest, labels)]
        if guest.passport:
            meta.append(f"{labels['passport']} {guest.passport}")
        who = [
            Paragraph(_esc(guest.name), s["value"]),
            Paragraph(_esc(" · ".join(meta)), s["muted"]),
        ]
        row = [Paragraph(str(i), s["muted"]), who]
        if with_treatment:
            if guest.treatment:
                what = [Paragraph(_esc(guest.treatment), s["value"])]
                if guest.treatment_detail:
                    detail = guest.treatment_detail
                    if compact and len(detail) > 90:
                        detail = detail[:88].rstrip(" ,.;:") + "…"
                    what.append(Paragraph(_esc(detail), s["muted"]))
            else:
                what = [Paragraph(_esc(labels["stay_only"]), s["muted"])]
            row.append(what)
        rows.append(row)

    if with_treatment:
        head = [
            Paragraph("№", s["label"]),
            Paragraph(labels["col_guest"], s["label"]),
            Paragraph(labels["col_treatment"], s["label"]),
        ]
        widths = [7 * mm, _CONTENT_W * 0.36, _CONTENT_W * 0.64 - 7 * mm]
        title = labels["guests_treatment"]
        data = [head, *rows]
    else:
        widths = [7 * mm, _CONTENT_W - 7 * mm]
        title = labels["guest_list"]
        data = rows
    table = Table(data, colWidths=widths)
    table.setStyle(
        _plain(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -2), 0.5, _LINE),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (1, 0), (1, -1), 10),
            ]
        )
    )
    return [KeepTogether([Paragraph(title, s["h"]), table])]


def _guest_kind(guest: _Guest, labels: dict[str, str]) -> str:
    if not guest.is_child:
        return labels["adult"]
    if guest.child_age is not None:
        return labels["child_age"].format(age=guest.child_age)
    return labels["child"]


def _payment(s, ctx: _Ctx, booking: Booking) -> list:
    labels = ctx.labels
    currency = ctx.invoice["currency"]
    items = ctx.invoice["line_items"]
    out: list = [Paragraph(labels["payment"], s["h"])]
    # A single line would only repeat the total; list lines only when they add up.
    if len(items) > 1:
        data = [
            [
                Paragraph(_esc(_line_label(item, ctx, booking)), s["base"]),
                Paragraph(_fmt_money(item["amount"], currency, ctx.lang), s["right"]),
            ]
            for item in items
        ]
        lines = Table(data, colWidths=[_CONTENT_W * 0.65, _CONTENT_W * 0.35])
        lines.setStyle(
            _plain(
                [
                    ("LINEBELOW", (0, 0), (-1, -1), 0.5, _LINE),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        out += [lines, Spacer(1, 5)]

    paid = booking.status in (BookingStatus.CONFIRMED, BookingStatus.COMPLETED)
    total = Table(
        [
            [
                Paragraph(
                    labels["paid"] if paid else labels["total"], s["total_label"]
                ),
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
                ("LEFTPADDING", (0, 0), (-1, -1), 11),
                ("RIGHTPADDING", (0, 0), (-1, -1), 11),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("ROUNDEDCORNERS", [6, 6, 6, 6]),
            ]
        )
    )
    notes = []
    if paid:
        notes.append(labels["pay_done"])
    elif booking.status == BookingStatus.PENDING:
        notes.append(labels["pay_how"])
    notes.append(labels["extras_note"])
    out += [total, Spacer(1, 4), Paragraph(_esc(" ".join(notes)), s["muted"])]
    return [KeepTogether(out)]


def _footer_grid(s, ctx: _Ctx, booking: Booking) -> list:
    """Cancellation · arrival · contacts side by side, under one rule."""
    labels = ctx.labels
    sanatorium = ctx.sanatorium

    cancel = [Paragraph(labels["cancellation"], s["h_cell"])]
    cancel += [Paragraph(_esc(t), s["cell"]) for t in _cancellation_lines(booking, ctx)]

    arrival = [Paragraph(labels["arrival"], s["h_cell"])]
    if sanatorium is not None:
        lines: list[str] = []
        if sanatorium.check_in_time is not None:
            lines.append(
                labels["checkin_from"].format(
                    t=sanatorium.check_in_time.strftime("%H:%M")
                )
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
        arrival += [Paragraph(_esc(t), s["cell"]) for t in lines]
        rules = pick_locale(sanatorium.house_rules, ctx.lang)
        if rules:
            arrival.append(Spacer(1, 2))
            arrival.append(Paragraph(_esc(rules), s["muted"]))

    if len(arrival) == 1:
        arrival = []

    contacts = [Paragraph(labels["contacts"], s["h_cell"])]
    prop: list[str] = []
    if sanatorium is not None:
        prop += [str(p) for p in (sanatorium.phones or []) if p]
        if sanatorium.customer_support_email:
            prop.append(sanatorium.customer_support_email)
    if prop:
        contacts.append(Paragraph(labels["property"], s["label"]))
        contacts += [Paragraph(_esc(p), s["cell"]) for p in prop]
        contacts.append(Spacer(1, 3))
    contacts.append(Paragraph(labels["support"], s["label"]))
    contacts.append(Paragraph(_esc(settings.SUPPORT_EMAIL), s["cell"]))
    if settings.SUPPORT_PHONE:
        contacts.append(Paragraph(_esc(settings.SUPPORT_PHONE), s["cell"]))

    grid = Table(
        [[cancel, arrival, contacts]],
        colWidths=[_CONTENT_W * 0.34, _CONTENT_W * 0.36, _CONTENT_W * 0.30],
    )
    grid.setStyle(
        _plain(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("RIGHTPADDING", (0, 0), (1, 0), 12),
            ]
        )
    )
    return [KeepTogether([Spacer(1, 12), _rule(_LINE, 0.8), Spacer(1, 8), grid])]


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
        guests=await _load_guests(db, booking, invoice, lang),
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


async def _load_guests(
    db: AsyncSession, booking: Booking, invoice: dict, lang: str
) -> list[_Guest]:
    """Guests in booking order, each with the program they were booked onto.

    guest_details is a flat list in (room, guest) order — the same order as the
    offer snapshot's per-guest inclusions. The program is re-read from
    treatment_selections so its name prints in the voucher's language; the
    snapshot title (frozen in the language the guest booked in) is the fallback.
    """
    slots = _snapshot_guests(booking)
    selected = {
        (sel.get("room_index", 0), sel.get("guest_index", 0)): sel.get("program_id")
        for sel in booking.treatment_selections or []
        if isinstance(sel, dict) and sel.get("program_id")
    }
    programs: dict[str, TreatmentProgram] = {}
    if selected:
        rows = await db.scalars(
            select(TreatmentProgram).where(
                TreatmentProgram.id.in_({str(v) for v in selected.values()})
            )
        )
        programs = {str(p.id): p for p in rows}

    details = [gd for gd in booking.guest_details or [] if isinstance(gd, dict)]
    guests: list[_Guest] = []
    for i, gd in enumerate(details):
        name = (gd.get("full_name") or "").strip()
        if not name:
            continue
        slot = slots[i] if i < len(slots) else {}
        guest = _Guest(
            name=name,
            passport=(gd.get("passport") or "").strip(),
            is_child=slot.get("type") == "child",
            child_age=slot.get("age"),
            treatment=slot.get("title", ""),
            treatment_detail=slot.get("detail", ""),
        )
        program = programs.get(str(selected.get(slot.get("key"), "")))
        if program is not None:
            guest.treatment = pick_locale(program.name, lang) or guest.treatment
            guest.treatment_detail = (
                pick_locale(program.description, lang) or guest.treatment_detail
            )
        guests.append(guest)
    if not guests and invoice["customer_name"]:
        slot = slots[0] if slots else {}
        guests.append(
            _Guest(
                name=invoice["customer_name"],
                treatment=slot.get("title", ""),
                treatment_detail=slot.get("detail", ""),
            )
        )
    return guests


def _snapshot_guests(booking: Booking) -> list[dict]:
    """Per-guest facts from the offer snapshot, in (room, guest) order."""
    inclusions = (booking.offer_snapshot or {}).get("inclusions") or []

    def _key(entry: dict):
        guest = entry.get("guest") or {}
        return (entry.get("room_index", 0), guest.get("guest_index", 0))

    out: list[dict] = []
    for entry in sorted(inclusions, key=_key):
        guest = entry.get("guest") or {}
        slot = {"key": _key(entry), "type": guest.get("type"), "age": guest.get("age")}
        for item in entry.get("items") or []:
            if item.get("type") in ("treatment", "special_package"):
                title = (item.get("title") or "").strip()
                if title:
                    slot["title"] = title
                    slot["detail"] = (item.get("description") or "").strip()
                    break
        out.append(slot)
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
