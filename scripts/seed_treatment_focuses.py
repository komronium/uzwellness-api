"""Seed treatment focus catalog and link existing treatment programs.

Usage:
    uv run python -m scripts.seed_treatment_focuses

This script is safe for existing server data:
    - upserts treatment focus catalog rows by slug;
    - writes demo SVG files for focus cards;
    - links only programs that currently have focus_id = NULL.

Use --relink to recompute focus_id for all programs.
"""

from __future__ import annotations

import argparse
import asyncio
from html import escape
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import Sanatorium, TreatmentFocus, TreatmentProgram


def tr(uz: str, ru: str, en: str) -> dict[str, str]:
    return {"uz": uz, "ru": ru, "en": en}


TREATMENT_FOCUSES = [
    {
        "slug": "cardiovascular",
        "name": tr("Yurak-qon tomir", "Кардиология", "Cardiovascular care"),
        "description": tr(
            "Kardiolog nazorati, EKG va yengil kardio tiklanish dasturlari.",
            "Наблюдение кардиолога, ЭКГ и легкие программы восстановления.",
            "Cardiologist supervision, ECG, and gentle cardiac recovery programs.",
        ),
        "image_url": "/uploads/demo/treatment-focuses/cardiovascular.svg",
        "icon": "heart-pulse",
        "display_order": 1,
    },
    {
        "slug": "digestive",
        "name": tr("Hazm qilish salomatligi", "Пищеварение", "Digestive health"),
        "description": tr(
            "Dietolog maslahati, mineral suv va individual ovqatlanish rejasi.",
            "Консультации диетолога, минеральная вода и индивидуальное питание.",
            "Dietitian guidance, mineral water, and individual meal planning.",
        ),
        "image_url": "/uploads/demo/treatment-focuses/digestive.svg",
        "icon": "stethoscope",
        "display_order": 2,
    },
    {
        "slug": "musculoskeletal",
        "name": tr(
            "Tayanch-harakat tizimi",
            "Опорно-двигательная система",
            "Musculoskeletal",
        ),
        "description": tr(
            "Bo'g'im, mushak va umurtqa uchun mineral vanna va fizioterapiya.",
            "Минеральные ванны и физиотерапия для суставов, мышц и позвоночника.",
            "Mineral baths and physiotherapy for joints, muscles, and spine.",
        ),
        "image_url": "/uploads/demo/treatment-focuses/musculoskeletal.svg",
        "icon": "bone",
        "display_order": 3,
    },
    {
        "slug": "respiratory",
        "name": tr("Nafas terapiyasi", "Респираторная терапия", "Respiratory therapy"),
        "description": tr(
            "Inhalatsiya, tog' havosi va o'pka reabilitatsiyasi.",
            "Ингаляции, горный воздух и легочная реабилитация.",
            "Inhalation, mountain air, and lung rehabilitation.",
        ),
        "image_url": "/uploads/demo/treatment-focuses/respiratory.svg",
        "icon": "lungs",
        "display_order": 4,
    },
    {
        "slug": "neurological",
        "name": tr("Nevrologik tiklanish", "Неврология", "Neurological recovery"),
        "description": tr(
            "Stressni kamaytirish, uyqu va asab tizimini tiklash dasturlari.",
            "Снижение стресса, сон и восстановление нервной системы.",
            "Stress reduction, sleep, and nervous system recovery programs.",
        ),
        "image_url": "/uploads/demo/treatment-focuses/neurological.svg",
        "icon": "brain",
        "display_order": 5,
    },
    {
        "slug": "wellness",
        "name": tr("Wellness va profilaktika", "Wellness и профилактика", "Wellness"),
        "description": tr(
            "Yoga, spa, meditatsiya va umumiy tiklanish dasturlari.",
            "Йога, спа, медитация и общие программы восстановления.",
            "Yoga, spa, meditation, and general recovery programs.",
        ),
        "image_url": "/uploads/demo/treatment-focuses/wellness.svg",
        "icon": "leaf",
        "display_order": 6,
    },
    {
        "slug": "dermatology",
        "name": tr("Dermatologiya", "Дерматология", "Dermatology"),
        "description": tr(
            "Teri salomatligi uchun mineral suv va shifokor nazorati.",
            "Минеральная вода и медицинский контроль для здоровья кожи.",
            "Mineral water and medical supervision for skin health.",
        ),
        "image_url": "/uploads/demo/treatment-focuses/dermatology.svg",
        "icon": "sparkles",
        "display_order": 7,
    },
    {
        "slug": "endocrine",
        "name": tr("Endokrinologiya", "Эндокринология", "Endocrine support"),
        "description": tr(
            "Metabolizm, vazn nazorati va diet terapiya dasturlari.",
            "Метаболизм, контроль веса и диетотерапия.",
            "Metabolism, weight control, and diet therapy programs.",
        ),
        "image_url": "/uploads/demo/treatment-focuses/endocrine.svg",
        "icon": "activity",
        "display_order": 8,
    },
]


KEYWORDS = {
    "cardiovascular": (
        "cardio",
        "cardiovascular",
        "kardio",
        "yurak",
        "heart",
        "ekg",
        "ecg",
        "кардио",
        "серд",
        "экг",
    ),
    "digestive": (
        "digest",
        "diet",
        "dietitian",
        "nutrition",
        "hazm",
        "ovqat",
        "dietolog",
        "пищевар",
        "диет",
        "питани",
    ),
    "musculoskeletal": (
        "musculoskeletal",
        "mineral bath",
        "bath",
        "joint",
        "muscle",
        "spine",
        "physio",
        "hydro",
        "vanna",
        "bo'g'im",
        "mushak",
        "fizioterapiya",
        "gidro",
        "сустав",
        "мышц",
        "ванн",
        "физио",
        "гидро",
    ),
    "respiratory": (
        "respir",
        "lung",
        "breath",
        "inhal",
        "pulmon",
        "nafas",
        "o'pka",
        "ингал",
        "респиратор",
        "легоч",
        "дых",
    ),
    "neurological": (
        "neuro",
        "stress",
        "sleep",
        "mindfulness",
        "meditation",
        "meditatsiya",
        "asab",
        "нерв",
        "невро",
        "сон",
        "стресс",
        "медитац",
    ),
    "wellness": (
        "wellness",
        "spa",
        "yoga",
        "retreat",
        "leisure",
        "recovery",
        "dam olish",
        "tiklanish",
        "йога",
        "спа",
        "отдых",
        "восстанов",
    ),
    "dermatology": ("skin", "dermat", "teri", "кож", "дермат"),
    "endocrine": ("endocr", "metabol", "weight", "vazn", "эндокрин", "метабол"),
}


def demo_media_file(url: str, title: str) -> None:
    prefix = settings.UPLOAD_URL_PREFIX.rstrip("/") + "/"
    if not url.startswith(prefix):
        return
    relative = url[len(prefix) :]
    path = Path(settings.UPLOAD_DIR) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_title = escape(title)
    path.write_text(
        "\n".join(
            [
                '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800" viewBox="0 0 1200 800">',
                '<defs><linearGradient id="g" x1="0" x2="1" y1="0" y2="1"><stop stop-color="#356653"/><stop offset="1" stop-color="#061b15"/></linearGradient></defs>',
                '<rect width="1200" height="800" fill="url(#g)"/>',
                '<circle cx="940" cy="180" r="120" fill="#d4b65f" opacity=".35"/>',
                '<path d="M0 610 C240 510 380 710 620 560 C850 420 980 620 1200 500 L1200 800 L0 800 Z" fill="#ffffff" opacity=".18"/>',
                f'<text x="80" y="620" font-family="Arial, sans-serif" font-size="58" font-weight="700" fill="#ffffff">{safe_title}</text>',
                '<text x="80" y="682" font-family="Arial, sans-serif" font-size="28" fill="#e8f2ee">UzWellness treatment focus</text>',
                "</svg>",
            ]
        ),
        encoding="utf-8",
    )


def _flatten_text(*values: object) -> str:
    parts: list[str] = []
    for value in values:
        if isinstance(value, dict):
            parts.extend(str(v) for v in value.values() if v)
        elif isinstance(value, list):
            parts.extend(str(v) for v in value if v)
        elif value:
            parts.append(str(value))
    return " ".join(parts).lower()


def _infer_focus_slug(program: TreatmentProgram, sanatorium: Sanatorium) -> str | None:
    text = _flatten_text(
        program.name,
        program.description,
        program.instructor_bio,
        program.what_to_bring,
        sanatorium.treatment_focuses,
    )
    for slug, keywords in KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return slug
    for slug in sanatorium.treatment_focuses or []:
        if slug in KEYWORDS:
            return slug
    return None


async def upsert_focuses(db) -> dict[str, TreatmentFocus]:
    existing = {
        row.slug: row
        for row in (await db.execute(select(TreatmentFocus))).scalars().all()
    }
    created = 0
    updated = 0
    for data in TREATMENT_FOCUSES:
        focus = existing.get(data["slug"])
        if focus is None:
            focus = TreatmentFocus(slug=data["slug"])
            db.add(focus)
            existing[data["slug"]] = focus
            created += 1
        else:
            updated += 1
        demo_media_file(data["image_url"], data["name"]["en"])
        focus.name = data["name"]
        focus.description = data["description"]
        focus.image_url = data["image_url"]
        focus.icon = data["icon"]
        focus.display_order = data["display_order"]
        focus.is_active = True
    await db.flush()
    print(f"Treatment focuses: created={created}, updated={updated}")
    return existing


async def link_programs(
    db, focuses: dict[str, TreatmentFocus], *, relink: bool
) -> tuple[int, int]:
    rows = (
        await db.execute(
            select(TreatmentProgram, Sanatorium).join(
                Sanatorium, TreatmentProgram.sanatorium_id == Sanatorium.id
            )
        )
    ).all()
    linked = 0
    skipped = 0
    for program, sanatorium in rows:
        if program.focus_id is not None and not relink:
            skipped += 1
            continue
        slug = _infer_focus_slug(program, sanatorium)
        focus = focuses.get(slug or "")
        if focus is None:
            skipped += 1
            continue
        program.focus_id = focus.id
        linked += 1
    return linked, skipped


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--relink",
        action="store_true",
        help="Recompute focus_id for all programs, including already linked ones.",
    )
    args = parser.parse_args()

    async with SessionLocal() as db:
        focuses = await upsert_focuses(db)
        linked, skipped = await link_programs(db, focuses, relink=args.relink)
        await db.commit()
    print(f"Treatment programs linked={linked}, skipped={skipped}")


if __name__ == "__main__":
    asyncio.run(main())
