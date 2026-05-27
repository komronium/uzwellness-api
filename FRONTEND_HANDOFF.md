# Frontend Handoff: Sanatorium Detail Enrichment

This document explains the backend changes added for richer sanatorium and room detail pages. The main goal is to let the frontend build hotel-detail pages closer to Sanatoriums.com and Trip.com: medical base, treatment profile, services, policies, trust badges, richer gallery metadata, room features, and rating breakdowns.

## Locale Behavior

Public endpoints return localized strings based on the existing locale dependency. Admin endpoints and `include_translations=true` return translation dictionaries.

Use the public localized response for customer-facing pages. Use admin responses for CMS/edit forms.

## Sanatorium Endpoints

Relevant endpoints:

- `GET /api/sanatoriums`
- `GET /api/sanatoriums/{sanatorium_id}`
- `POST /api/sanatoriums`
- `PATCH /api/sanatoriums/{sanatorium_id}`

OpenAPI now documents list/detail responses as:

- `SanatoriumList | SanatoriumAdminList`
- `SanatoriumRead | SanatoriumAdminRead`

That means frontend API clients should now see real response schemas instead of `{}` for public list/detail endpoints.

## New Sanatorium Fields

### `medical_base`

Customer-facing medical facility details.

Public response shape:

```json
{
  "description": "Includes a doctor check, basic diagnostics, and a daily treatment schedule.",
  "procedures_per_week": 12,
  "min_age_for_treatment": 18,
  "checkups_included": 2,
  "natural_resources": ["mineral_water", "mountain_air"],
  "procedures": {
    "core": [
      {
        "code": "respiratory_rehab",
        "image_url": "/uploads/demo/procedures/respiratory.jpg",
        "description": "Inhalation, speleotherapy, and forest walks for respiratory rehabilitation."
      }
    ],
    "additional": []
  },
  "stay_inclusions": [
    {"min_days": 3, "inclusions": ["doctor_check", "meal_plan"]},
    {"min_days": 7, "inclusions": ["doctor_check", "diagnostics", "treatment_plan"]}
  ]
}
```

Frontend usage:

- Show as a "Medical base" or "Treatment facilities" section.
- Group `procedures` by category keys such as `core` and `additional`.
- Render `natural_resources` as chips. The current values are stable codes, not translated labels, so map them on frontend if needed.
- `stay_inclusions` is useful for package comparison cards: "from 3 days includes doctor check".

### `treatment_profile`

Explains what the sanatorium treats and what diagnostics/specialists are available.

Public response shape:

```json
{
  "main_indications": [
    {
      "code": "respiratory",
      "title": "Respiratory system",
      "description": "A doctor prepares an individual plan."
    }
  ],
  "additional_indications": [],
  "contraindications": [],
  "diagnostics": ["doctor_consultation", "blood_pressure", "ecg"],
  "doctor_specialties": ["therapist", "physiotherapist", "dietitian"],
  "notes": "The program is finalized after the doctor's check on arrival day."
}
```

Frontend usage:

- Use `main_indications` for primary treatment cards.
- Use `additional_indications` as secondary chips/list.
- Show `contraindications` in a careful info block.
- `diagnostics` and `doctor_specialties` are code arrays; map codes to UI labels.

### `service_matrix`

Trip.com-style facility/service breakdown grouped by category.

Public response shape:

```json
{
  "food_drink": {
    "title": "Food and drink",
    "items": [
      {
        "code": "restaurant",
        "title": "Restaurant",
        "description": "Restaurant is available.",
        "is_available": true,
        "cost": "free",
        "hours": "07:00-22:00",
        "location": "Archazor Restaurant",
        "icon": "utensils",
        "tags": []
      }
    ]
  },
  "wellness": {"title": "Wellness", "items": []},
  "medical_department": {"title": "Medical department", "items": []},
  "front_desk": {"title": "Front desk", "items": []},
  "cleaning": {"title": "Cleaning", "items": []},
  "business": {"title": "Business", "items": []},
  "parking": {"title": "Parking", "items": []},
  "internet": {"title": "Internet", "items": []},
  "children": {"title": "Children", "items": []},
  "accessibility": {"title": "Accessibility", "items": []},
  "languages": ["uz", "ru", "en"],
  "notes": "Services may vary by season and occupancy."
}
```

Frontend usage:

- Render only groups with at least one `items` entry, except `languages` and `notes`.
- `cost` uses amenity cost values such as `free`, `paid`, `on_request`.
- `icon` is a semantic icon key. It is safe to map to frontend icon components.
- `is_available=false` can be shown as disabled/unavailable if later added by admin.

### `policies`

Detailed rules and booking policies.

Public/admin response shape is structured:

```json
{
  "check_in": {
    "instructions": {"uz": "...", "ru": "...", "en": "..."},
    "required_documents": ["passport", "medical_summary"],
    "notes": {}
  },
  "children": {
    "allowed": true,
    "min_age": 0,
    "treatment_min_age": 18,
    "notes": {}
  },
  "extra_bed": {
    "available": true,
    "crib_available": false,
    "price": "18.00",
    "currency": "USD",
    "notes": {}
  },
  "breakfast": {
    "included": true,
    "price": null,
    "currency": null,
    "style": "buffet",
    "hours": "07:00-10:00",
    "notes": {}
  },
  "pets": {
    "allowed": false,
    "service_animals_allowed": true,
    "fee": null,
    "currency": null,
    "notes": {}
  },
  "cancellation": {
    "free_cancellation_until_days_before": 5,
    "penalty_percent": "50.00",
    "notes": {}
  },
  "payment": {
    "methods": ["cash", "bank_transfer", "uzcard", "visa"],
    "deposit_required": true,
    "deposit_percent": "20.00",
    "notes": {}
  },
  "fees": {
    "mandatory_fees": ["resort_registration"],
    "optional_fees": ["airport_transfer", "additional_procedures"],
    "notes": {}
  }
}
```

Frontend usage:

- Keep this as a "Policies" accordion.
- Some nested `notes`, `instructions` are translation dictionaries, even in public response. If a localized string is needed, use the current app locale to pick `uz`, `ru`, or `en`.
- Continue showing old top-level fields like `check_in_time`, `check_out_time`, `pets_allowed`, `payment_methods` for summary UI; use `policies` for detailed UI.

### `promo_badges`

Trust/benefit badges for detail cards and page header.

Public response shape:

```json
[
  {
    "code": "doctor_checked",
    "kind": "trust",
    "title": "Doctor supervised",
    "description": "Treatment programs are assigned after a doctor's check.",
    "icon": "stethoscope",
    "is_active": true,
    "priority": 10,
    "valid_until": null
  }
]
```

Frontend usage:

- Sort by `priority` ascending if needed.
- Public response filters inactive badges.
- `kind` can drive color/tone: `trust`, `benefit`, `info`, etc.
- `icon` is a semantic icon key.

### `rating_breakdown`

Automatically calculated from visible reviews.

Response shape:

```json
{
  "cleanliness": "4.50",
  "amenities": "4.50",
  "location": "4.50",
  "service": "4.50",
  "treatment": "4.50",
  "value": "3.50",
  "food": "4.50"
}
```

Frontend usage:

- Use for Trip.com-style rating bars.
- Values may be `null` when there are no visible reviews.
- Backend recalculates after reviews are created/updated/hidden.

## Room Endpoints

Relevant endpoints:

- `GET /api/rooms?sanatorium_id=...`
- `GET /api/rooms/{room_id}`
- `POST /api/rooms`
- `PATCH /api/rooms/{room_id}`

OpenAPI now documents list/detail responses as:

- `RoomList | RoomAdminList`
- `RoomRead | RoomAdminRead`

## New Room Field

### `room_features`

Detailed room facilities for richer room cards and room detail modals.

Response shape:

```json
{
  "has_window": true,
  "bathroom": {
    "private": true,
    "type": "shower",
    "bidet": false,
    "toiletries": true,
    "hairdryer": true,
    "bathrobe": false,
    "slippers": true
  },
  "climate": {
    "air_conditioning": true,
    "heating": true
  },
  "kitchen": {
    "refrigerator": true,
    "minibar": true,
    "kettle": true,
    "kitchenette": false
  },
  "accessibility": {
    "wheelchair_accessible": false,
    "roll_in_shower": false,
    "grab_bars": false,
    "visual_alarm": false
  },
  "safety": {
    "safe": true,
    "smoke_detector": true,
    "smart_lock": true
  },
  "entertainment": {
    "tv": true,
    "smart_tv": true,
    "satellite_channels": true
  },
  "comfort": {
    "balcony": true,
    "terrace": false,
    "desk": true,
    "sofa": false,
    "carpet": true
  },
  "highlights": ["compact_comfort", "mountain_view"]
}
```

Frontend usage:

- Show a short subset on room cards: size, view, bed, bathroom, balcony, air conditioning.
- Show the full grouped list in a room detail modal.
- `bathroom.type` values: `shower`, `bathtub`, `shower_and_bathtub`.
- `highlights` are stable codes; map to labels.

## Gallery/Image Metadata

Sanatorium and room images now include richer metadata.

Fields:

```json
{
  "is_360": false,
  "category": "bedroom",
  "caption": "Pine Standard bedroom",
  "caption_i18n": {"uz": "...", "ru": "...", "en": "..."},
  "alt_text": {"uz": "...", "ru": "...", "en": "..."},
  "tags": ["zomin-shifo-resort", "room", "bedroom"]
}
```

Room images also keep the existing `is_video` field.

Frontend usage:

- Use `category` for gallery filters: exterior, treatment, surroundings, bedroom, tour.
- Use `is_360=true` to show a 360 badge or open a tour viewer.
- Use `is_video=true` for video player behavior.
- Use `alt_text[locale]` for image alt text; fallback to `caption_i18n[locale]`, then `caption`.
- Use `tags` for gallery grouping/search if needed.

Upload/update endpoints accept JSON strings in multipart form fields:

- `caption_i18n`
- `alt_text`
- `tags`

Example multipart values:

```json
caption_i18n={"uz":"Xona","ru":"Номер","en":"Room"}
alt_text={"uz":"Xona rasmi","ru":"Фото номера","en":"Room photo"}
tags=["room","bedroom"]
```

## Admin Create/Patch Payloads

Admin create/patch supports these new fields:

- `medical_base`
- `treatment_profile`
- `service_matrix`
- `policies`
- `promo_badges`
- `room_features`

All fields have defaults, so existing frontend create/edit forms do not have to send them immediately. The frontend can add these sections gradually.

## Demo Data

`scripts/demo_data.py` now populates the new fields:

- Sanatorium medical base
- Treatment profile
- Service matrix
- Policies
- Promo badges
- Room features
- Image metadata
- Review rating breakdown

This should give frontend enough sample data to build and test the UI without manual DB edits.

## Recommended Frontend Sections

Suggested sanatorium detail page order:

1. Header: name, stars, location, primary badges, avg rating.
2. Gallery: categories, video/360 badges, image alt text.
3. Rooms: room features summary and full modal.
4. Treatment profile: main indications, diagnostics, specialists.
5. Medical base: procedures, natural resources, stay inclusions.
6. Services: grouped `service_matrix`.
7. Reviews: rating breakdown bars.
8. Policies: check-in, children, extra bed, breakfast, pets, cancellation, payment, fees.

## Backward Compatibility Notes

- Existing old fields remain available.
- New objects default to empty objects/lists when not configured.
- Public localized fields are strings, while admin fields are translation dictionaries.
- Rating breakdown values are decimals represented as strings in JSON.
- Some code arrays need frontend label maps: `natural_resources`, `diagnostics`, `doctor_specialties`, `highlights`.

