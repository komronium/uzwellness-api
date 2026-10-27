"""Fill uz/ru for catalog text that the seed scripts wrote in English only.

The seed helpers' `tr(en)` copied the English string into uz and ru, so the
public site showed English on /uz and /ru for rooms, rate plans, programs,
treatment focuses, policies, venues and image captions. This script walks every
translation object ({uz, ru, en}) in the affected columns and fills uz/ru from
a reviewed dictionary — only where uz/ru is empty or still a copy of en, so a
translation an admin typed is never overwritten.

Usage:
    uv run python -m scripts.translate_catalog_content
    uv run python -m scripts.translate_catalog_content --write

Without --write the script only reports what it would change and rolls back.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections import Counter
from typing import Any

from sqlalchemy import text

from app.core.database import SessionLocal

Pair = tuple[str, str]  # (uz, ru)

# Seed property name -> (uz name, ru name used after "санаторий"/"в санатории").
SANATORIUMS: dict[str, tuple[str, str]] = {
    "Zomin": ("Zomin", "Зомин"),
    "Chortoq": ("Chortoq", "Чартак"),
    "Chimyon": ("Chimyon", "Чимион"),
    "Chinobod": ("Chinobod", "Чинабад"),
    "Oq-Tosh": ("Oq-Tosh", "Акташ"),
    "Sitorai Mohi Hosa": ("Sitorai Mohi Hosa", "Ситораи Мохи Хоса"),
}

ROOM_TYPES: dict[str, Pair] = {
    "Comfort Twin": (
        "Komfort Twin (2 ta alohida karavot)",
        "Комфорт Twin (2 отдельные кровати)",
    ),
    "Deluxe Double Room": ("Deluxe ikki kishilik xona", "Делюкс двухместный номер"),
    "Family Suite": ("Oilaviy lyuks", "Семейный люкс"),
    "Standard Single": ("Standart bir kishilik xona", "Стандартный одноместный номер"),
}

EXACT: dict[str, Pair] = {
    **ROOM_TYPES,
    # amenities.description
    "Diet meals is available for this stay.": (
        "Parhez ovqatlanish taqdim etiladi.",
        "Предоставляется диетическое питание.",
    ),
    "Children corner is available for this stay.": (
        "Bolalar burchagi mavjud.",
        "Есть детский уголок.",
    ),
    "Mountain air is available for this stay.": (
        "Toza tog' havosi.",
        "Чистый горный воздух.",
    ),
    "Walking garden is available for this stay.": (
        "Sayr qilish uchun bog' mavjud.",
        "Есть парк для прогулок.",
    ),
    "Therapeutic baths is available for this stay.": (
        "Davolovchi vannalar mavjud.",
        "Доступны лечебные ванны.",
    ),
    "Transfer desk is available for this stay.": (
        "Transfer xizmati mavjud.",
        "Доступна служба трансфера.",
    ),
    "Mineral baths and therapeutic showers.": (
        "Mineral vannalar va davolovchi dush.",
        "Минеральные ванны и лечебные души.",
    ),
    "Manual massage procedures.": (
        "Qo'l massaji muolajalari.",
        "Процедуры ручного массажа.",
    ),
    "Private in-room bathroom.": (
        "Xona ichida alohida hammom.",
        "Отдельная ванная комната в номере.",
    ),
    "In-room air conditioning.": ("Xonada konditsioner.", "Кондиционер в номере."),
    "In-room TV.": ("Xonada televizor.", "Телевизор в номере."),
    "Small in-room refrigerator.": (
        "Xonada kichik muzlatkich.",
        "Небольшой холодильник в номере.",
    ),
    "Room balcony.": ("Xonada balkon.", "Балкон в номере."),
    "Transfer can be arranged by request.": (
        "So'rov bo'yicha transfer tashkil qilinadi.",
        "Трансфер организуется по запросу.",
    ),
    # extra beds / policies
    "Baby crib for children up to 4 years old.": (
        "4 yoshgacha bolalar uchun beshik.",
        "Детская кроватка для детей до 4 лет.",
    ),
    "Portable extra bed with linen.": (
        "Choyshabli ko'chma qo'shimcha karavot.",
        "Переносная дополнительная кровать с постельным бельём.",
    ),
    "Child meal and stay supplement.": (
        "Bola uchun ovqat va turar joy qo'shimcha to'lovi.",
        "Доплата за питание и проживание ребёнка.",
    ),
    "Doctor consultation required": (
        "Shifokor konsultatsiyasi talab qilinadi",
        "Требуется консультация врача",
    ),
    "Free when sharing existing bed.": (
        "Mavjud karavotda birga yotsa — bepul.",
        "Бесплатно при размещении на существующей кровати.",
    ),
    "Passport and medical documents are required at check-in.": (
        "Joylashishda pasport va tibbiy hujjatlar talab qilinadi.",
        "При заселении необходимы паспорт и медицинские документы.",
    ),
    "Treatment procedures are assigned after a doctor consultation.": (
        "Davolash muolajalari shifokor konsultatsiyasidan keyin belgilanadi.",
        "Лечебные процедуры назначаются после консультации врача.",
    ),
    # venues / surroundings
    "Dining hall": ("Ovqatlanish zali", "Обеденный зал"),
    "Medical block": ("Tibbiyot bloki", "Медицинский корпус"),
    "Wellness zone": ("Wellness zonasi", "Велнес-зона"),
    "Walking area": ("Sayr qilish hududi", "Прогулочная зона"),
    "Bostanliq center": ("Bo'stonliq markazi", "Центр Бостанлыка"),
    "Bukhara center": ("Buxoro markazi", "Центр Бухары"),
    "Chortoq center": ("Chortoq markazi", "Центр Чартака"),
    "Fergana center": ("Farg'ona markazi", "Центр Ферганы"),
    "Tashkent center": ("Toshkent markazi", "Центр Ташкента"),
    "Zomin center": ("Zomin markazi", "Центр Зомина"),
    # package items / packages / promotions / rate plans
    "Arrival transfer can be arranged by the booking office.": (
        "Kelish transferini bron bo'limi tashkil qiladi.",
        "Трансфер по прибытии организует отдел бронирования.",
    ),
    "Doctor consultation and daily procedures.": (
        "Shifokor konsultatsiyasi va kundalik muolajalar.",
        "Консультация врача и ежедневные процедуры.",
    ),
    "Three balanced meals per day.": (
        "Kuniga uch mahal muvozanatli ovqatlanish.",
        "Трёхразовое сбалансированное питание.",
    ),
    "Basic cure package": ("Asosiy davolash paketi", "Базовый лечебный пакет"),
    "Full board diet meals": (
        "To'liq pansion, parhez ovqatlanish",
        "Полный пансион, диетическое питание",
    ),
    "Transfer assistance": ("Transferda yordam", "Помощь с трансфером"),
    "Seven nights with accommodation, full board, treatment package, and transfer help.": (
        "Yetti kecha: turar joy, to'liq pansion, davolash paketi va transferda yordam.",
        "Семь ночей: проживание, полный пансион, лечебный пакет и помощь с трансфером.",
    ),
    "Long-stay wellness discount": (
        "Uzoq muddatli dam olish uchun chegirma",
        "Скидка за длительное проживание",
    ),
    "Full board and treatment": (
        "To'liq pansion va davolash",
        "Полный пансион и лечение",
    ),
    "Half board and treatment": ("Yarim pansion va davolash", "Полупансион и лечение"),
    # treatment focuses
    "Cardiovascular recovery": (
        "Yurak-qon tomir tizimini tiklash",
        "Восстановление сердечно-сосудистой системы",
    ),
    "Digestive health": ("Hazm tizimi salomatligi", "Здоровье пищеварения"),
    "Metabolic health": ("Moddalar almashinuvi salomatligi", "Здоровье обмена веществ"),
    "Musculoskeletal recovery": (
        "Tayanch-harakat tizimini tiklash",
        "Восстановление опорно-двигательного аппарата",
    ),
    "Neurology": ("Nevrologiya", "Неврология"),
    "Respiratory health": (
        "Nafas olish tizimi salomatligi",
        "Здоровье органов дыхания",
    ),
    "Stress recovery": ("Stressdan tiklanish", "Восстановление после стресса"),
    "Urology": ("Urologiya", "Урология"),
    "endocrine and metabolism": (
        "endokrin tizim va moddalar almashinuvi",
        "эндокринная система и обмен веществ",
    ),
    "gastroenterology": ("gastroenterologiya", "гастроэнтерология"),
    "heart and vessels": ("yurak va qon tomirlar", "сердце и сосуды"),
    "joints and spine": ("bo'g'imlar va umurtqa pog'onasi", "суставы и позвоночник"),
    "kidney and urinary tract care": (
        "buyrak va siydik yo'llari",
        "почки и мочевыводящие пути",
    ),
    "lungs and clean air": ("o'pka va toza havo", "лёгкие и чистый воздух"),
    "Mineral-water and diet therapy.": (
        "Mineral suv va parhez bilan davolash.",
        "Лечение минеральной водой и диетой.",
    ),
    "nervous system recovery": (
        "asab tizimini tiklash",
        "восстановление нервной системы",
    ),
    "Quiet recreation and light wellness routines.": (
        "Sokin dam olish va yengil wellness mashg'ulotlari.",
        "Спокойный отдых и лёгкие велнес-процедуры.",
    ),
    "sleep and nervous system balance": (
        "uyqu va asab tizimi muvozanati",
        "баланс сна и нервной системы",
    ),
    # treatment programs
    "1 medical examination, 10 medical procedures, mineral-water or physiotherapy course": (
        "1 ta tibbiy ko'rik, 10 ta tibbiy muolaja, mineral suv yoki fizioterapiya kursi",
        "1 медицинский осмотр, 10 медицинских процедур, курс минеральной воды "
        "или физиотерапии",
    ),
    "1 medical examination, 6 medical procedures, access to wellness": (
        "1 ta tibbiy ko'rik, 6 ta tibbiy muolaja, wellness zonasidan foydalanish",
        "1 медицинский осмотр, 6 медицинских процедур, доступ к велнес-зоне",
    ),
    "pool access, sauna entry, walking garden access": (
        "basseyn, sauna va sayr bog'idan foydalanish",
        "бассейн, сауна и прогулочный парк",
    ),
    "Comfortable clothing and personal medical documents.": (
        "Qulay kiyim va shaxsiy tibbiy hujjatlar.",
        "Удобная одежда и личные медицинские документы.",
    ),
    # seed property descriptions / addresses
    "Bukhara wellness sanatorium with mineral-water, urology, and metabolic recovery programs.": (
        "Mineral suv, urologiya va moddalar almashinuvini tiklash dasturlariga ega "
        "Buxorodagi sanatoriya.",
        "Санаторий в Бухаре с программами лечения минеральной водой, урологии и "
        "восстановления обмена веществ.",
    ),
    "Mountain-climate sanatorium for respiratory recovery, sleep balance, and rehabilitation.": (
        "Nafas olish tizimini tiklash, uyquni me'yorlashtirish va reabilitatsiya uchun "
        "tog' iqlimidagi sanatoriya.",
        "Санаторий с горным климатом для восстановления дыхания, нормализации сна и "
        "реабилитации.",
    ),
    "Sitorai Mohi Hosa area, Bukhara Region, Uzbekistan": (
        "Buxoro viloyati, Sitorai Mohi Hosa hududi, O'zbekiston",
        "Бухарская область, район Ситораи Мохи Хоса, Узбекистан",
    ),
}

_S = "(?P<s>" + "|".join(re.escape(k) for k in SANATORIUMS) + ") Sanatorium"
_R = "(?P<r>" + "|".join(re.escape(k) for k in ROOM_TYPES) + ")"


def _pattern(en: str) -> Pair | None:
    def names(m: re.Match[str]) -> tuple[str, str]:
        return SANATORIUMS[m.group("s")]

    def room(m: re.Match[str]) -> Pair:
        return ROOM_TYPES[m.group("r")]

    rules: list[tuple[str, Any]] = [
        (
            rf"{_S}",
            lambda m: (f"{names(m)[0]} sanatoriyasi", f"Санаторий {names(m)[1]}"),
        ),
        (
            rf"{_S} photo (?P<n>\d+)",
            lambda m: (
                f"{names(m)[0]} sanatoriyasi — {m['n']}-rasm",
                f"Санаторий {names(m)[1]} — фото {m['n']}",
            ),
        ),
        (
            rf"{_S} wellness stay",
            lambda m: (
                f"{names(m)[0]} sanatoriyasida dam olish",
                f"Отдых в санатории {names(m)[1]}",
            ),
        ),
        (
            rf"{_S} 7-night recovery package",
            lambda m: (
                f"{names(m)[0]} sanatoriyasi — 7 kechalik tiklanish paketi",
                f"Санаторий {names(m)[1]} — восстановление, 7 ночей",
            ),
        ),
        (
            rf"{_S} Basic Cure",
            lambda m: (
                f"{names(m)[0]} sanatoriyasi: asosiy davolash kursi",
                f"Санаторий {names(m)[1]}: базовый курс лечения",
            ),
        ),
        (
            rf"{_S} Intensive Recovery",
            lambda m: (
                f"{names(m)[0]} sanatoriyasi: intensiv tiklanish kursi",
                f"Санаторий {names(m)[1]}: интенсивный восстановительный курс",
            ),
        ),
        (
            rf"{_S} Pool and Wellness Access",
            lambda m: (
                f"{names(m)[0]} sanatoriyasi: basseyn va wellness",
                f"Санаторий {names(m)[1]}: бассейн и велнес",
            ),
        ),
        (
            rf"{_R} at {_S} with private bathroom, Wi-Fi, and treatment access\.",
            lambda m: (
                f"{names(m)[0]} sanatoriyasidagi {room(m)[0]}: alohida hammom, "
                "Wi-Fi va davolanish imkoniyati.",
                f"{room(m)[1]} в санатории {names(m)[1]}: собственная ванная, "
                "Wi-Fi и доступ к лечению.",
            ),
        ),
        (
            rf"{_R} at {_S}",
            lambda m: (
                f"{names(m)[0]} sanatoriyasidagi {room(m)[0]}",
                f"{room(m)[1]} в санатории {names(m)[1]}",
            ),
        ),
        (
            rf"{_R} photo (?P<n>\d+)",
            lambda m: (
                f"{room(m)[0]} — {m['n']}-rasm",
                f"{room(m)[1]} — фото {m['n']}",
            ),
        ),
    ]
    for regex, build in rules:
        m = re.fullmatch(regex, en)
        if m:
            return build(m)
    return None


def translate(en: str) -> Pair | None:
    return EXACT.get(en) or _pattern(en)


COLUMNS: list[tuple[str, str]] = [
    ("amenities", "description"),
    ("extra_bed_configs", "name"),
    ("extra_bed_configs", "description"),
    ("package_items", "title"),
    ("package_items", "description"),
    ("packages", "title"),
    ("packages", "description"),
    ("promotions", "name"),
    ("rate_plans", "name"),
    ("rooms", "name"),
    ("rooms", "description"),
    ("room_images", "alt_text"),
    ("room_images", "caption_i18n"),
    ("sanatorium_images", "alt_text"),
    ("sanatorium_images", "caption_i18n"),
    ("sanatoriums", "name"),
    ("sanatoriums", "description"),
    ("sanatoriums", "address"),
    ("sanatoriums", "policies"),
    ("sanatoriums", "surroundings"),
    ("sanatoriums", "venues"),
    ("treatment_focuses", "name"),
    ("treatment_focuses", "description"),
    ("treatment_programs", "name"),
    ("treatment_programs", "description"),
    ("treatment_programs", "what_to_bring"),
]


def _needs(obj: dict, locale: str) -> bool:
    value = obj.get(locale)
    return not value or value == obj.get("en")


def patch(value: Any, stats: Counter, missing: Counter) -> Any:
    """Return `value` with every untranslated {uz, ru, en} object filled in."""
    if isinstance(value, list):
        return [patch(v, stats, missing) for v in value]
    if not isinstance(value, dict):
        return value
    en = value.get("en")
    if isinstance(en, str) and en and (_needs(value, "uz") or _needs(value, "ru")):
        pair = translate(en)
        if pair is None:
            missing[en] += 1
        else:
            value = dict(value)
            for locale, text_ in zip(("uz", "ru"), pair):
                if _needs(value, locale):
                    value[locale] = text_
                    stats["filled"] += 1
            return value
    return {k: patch(v, stats, missing) for k, v in value.items()}


async def run(write: bool) -> None:
    missing: Counter = Counter()
    async with SessionLocal() as db:
        for table, column in COLUMNS:
            stats: Counter = Counter()
            rows = (await db.execute(text(f"SELECT id, {column} FROM {table}"))).all()
            for row_id, value in rows:
                patched = patch(value, stats, missing)
                if patched != value:
                    stats["rows"] += 1
                    await db.execute(
                        text(
                            f"UPDATE {table} SET {column} = CAST(:v AS jsonb) WHERE id = :id"
                        ),
                        {"v": json.dumps(patched, ensure_ascii=False), "id": row_id},
                    )
            if stats:
                print(
                    f"{table}.{column}: {stats['rows']} rows, {stats['filled']} texts"
                )
        if write:
            await db.commit()
            print("Done.")
        else:
            await db.rollback()
            print("Dry run complete; rolled back.")
    if missing:
        print("\nNo translation for (left as is):")
        for en, count in sorted(missing.items()):
            print(f"  {count:3} × {en[:90]}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Persist changes. Without this flag the script rolls back.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args().write))
