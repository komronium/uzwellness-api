# Frontend Handoff: Homepage API Changes

This document only covers frontend-facing backend changes for homepage sections reviewed from search through curated journeys.

## 1. Search Bar

Use one sanatorium-level endpoint for the homepage search bar and search results.

```http
GET /api/sanatoriums/search
```

Query params:

```text
location: string | optional
check_in: YYYY-MM-DD | required
check_out: YYYY-MM-DD | required
adults: integer | default 2
children: integer | default 0
treatment_focus: string | optional
destination_id: uuid | optional
sanatorium_id: uuid | optional
limit: integer | default 20
offset: integer | default 0
lang: uz | ru | en | optional
```

Example:

```http
GET /api/sanatoriums/search?location=Boysun&check_in=2026-10-02&check_out=2026-10-05&adults=2&children=1&treatment_focus=cardiovascular
```

Response:

```json
{
  "items": [
    {
      "sanatorium_id": "uuid",
      "sanatorium_slug": "boysun-spa",
      "sanatorium_name": "Boysun Spa",
      "city": "Boysun",
      "region_id": "uuid",
      "region_name": "Surxondaryo",
      "destination_id": "uuid",
      "destination_name": "Boysun",
      "primary_image_url": "/uploads/sanatoriums/boysun.jpg",
      "stars": 4,
      "avg_rating": "4.70",
      "review_count": 7,
      "property_type": "sanatorium",
      "wellness_category": null,
      "treatment_focuses": ["cardiovascular"],
      "check_in": "2026-10-02",
      "check_out": "2026-10-05",
      "nights": 3,
      "adults": 2,
      "children": 1,
      "guests": 3,
      "available_room_id": "uuid",
      "available_room_name": "Standard",
      "rooms_count_needed": 2,
      "min_total_price": "600.00",
      "min_total_price_currency": "USD",
      "min_total_price_usd": "600.00"
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

Rules:

- `check_out` must be after `check_in`; otherwise backend returns `400`.
- `guests = adults + children`.
- `rooms_count_needed` is calculated from room capacity.
- Results include only approved sanatoriums with available active rooms.
- Availability respects blocked/booked units for every night in `[check_in, check_out)`.
- If UI selected "Any treatment", omit `treatment_focus`.
- Keep `/api/rooms/search` only for room-level availability inside a sanatorium detail page.

## 2. Destination Cards

Use this endpoint for the homepage destination cards.

```http
GET /api/destinations/tiles
```

Response item:

```json
{
  "id": "uuid",
  "slug": "chimgan-mountains",
  "name": "Chimgan Mountains",
  "tagline": "Mountain air, mineral water, and quiet recovery",
  "description": "Sanatoriums and resorts a short drive from Tashkent.",
  "hero_image_url": "/uploads/demo/destinations/chimgan.svg",
  "lat": "41.550000",
  "lng": "70.016700",
  "is_active": true,
  "created_at": "2026-05-28T10:00:00Z",
  "updated_at": "2026-05-28T10:00:00Z",
  "sanatoriums_count": 4,
  "min_price_usd": "48.00"
}
```

Rules:

- Public endpoints hide inactive destinations.
- Tiles are sorted by `sanatoriums_count DESC`, then creation time.
- `min_price_usd` ignores rooms with zero inventory.
- `country` was removed.
- `hero_image` was renamed to `hero_image_url`.
- `tagline` is the short subtitle for cards.

Destination image management:

```http
POST /api/destinations/{destination_id}/hero-image
DELETE /api/destinations/{destination_id}/hero-image
```

Upload uses multipart form data:

```text
file: string($binary)
```

Accepted formats:

```text
JPEG
PNG
WebP
```

Do not set `Content-Type` manually when uploading; browser must set the multipart boundary.

## 3. Treatment Cards

Use this endpoint for the treatment program cards section.

```http
GET /api/treatment-focuses/tiles
```

Response:

```json
{
  "items": [
    {
      "id": "uuid",
      "slug": "cardiovascular",
      "name": "Cardiovascular care",
      "description": "Cardiologist supervision, ECG, and gentle cardiac recovery programs.",
      "image_url": "/uploads/demo/treatment-focuses/cardiovascular.svg",
      "icon": "heart-pulse",
      "display_order": 1,
      "is_active": true,
      "created_at": "2026-05-28T10:00:00Z",
      "updated_at": "2026-05-28T10:00:00Z",
      "programs_count": 12,
      "sanatoriums_count": 4
    }
  ],
  "total": 1
}
```

Rules:

- Public list/detail hides inactive focuses.
- Cards are ordered by `display_order`.
- `programs_count` counts active programs attached to approved sanatoriums.
- `ProgramCreate` and `ProgramUpdate` now accept `focus_id`.
- If a focus is deleted, linked programs remain and `focus_id` becomes `null`.

Management endpoints:

```http
GET /api/treatment-focuses
GET /api/treatment-focuses/{slug_or_id}
POST /api/treatment-focuses
PATCH /api/treatment-focuses/{focus_id}
POST /api/treatment-focuses/{focus_id}/image
DELETE /api/treatment-focuses/{focus_id}/image
DELETE /api/treatment-focuses/{focus_id}
```

Only `super_admin` can create, update, upload/delete image, or delete treatment focuses.

Treatment seed script for server:

```bash
uv run python -m scripts.seed_treatment_focuses
```

Use `--relink` only if existing program `focus_id` values should be recomputed.

## 4. Curated Journeys

Use this endpoint for the homepage all-inclusive journey cards.

```http
GET /api/packages/featured
```

It returns active packages where `is_featured=true`, ordered by `display_order`.

Response item:

```json
{
  "id": "uuid",
  "slug": "zaamin-respiratory-retreat-7n",
  "title": "Zaamin 7-Night Respiratory Retreat",
  "description": "Accommodation, full board, doctor check, inhalation, and transfer included.",
  "hero_image_url": "/uploads/demo/packages/zaamin-retreat.svg",
  "duration_nights": 7,
  "base_price": "6800000.00",
  "currency": "UZS",
  "sanatorium_id": "uuid",
  "room_id": "uuid",
  "is_active": true,
  "is_featured": true,
  "display_order": 1,
  "items": [
    {
      "id": "uuid",
      "item_type": "treatment",
      "title": "Treatment program",
      "description": "Daily treatments prescribed by a doctor.",
      "is_included": true,
      "extra_price": null,
      "display_order": 1
    }
  ],
  "created_at": "2026-05-28T10:00:00Z",
  "updated_at": "2026-05-28T10:00:00Z"
}
```

Rules:

- Public `GET /api/packages` ignores `active_only=false`; inactive packages are hidden.
- Only authenticated `super_admin` can list/get inactive packages.
- Public package detail returns `404` for inactive packages.
- Package create/update no longer accepts `hero_image_url` as JSON.
- Use `POST /api/packages/{package_id}/hero-image` for package images.

Package image management:

```http
POST /api/packages/{package_id}/hero-image
DELETE /api/packages/{package_id}/hero-image
```

Upload uses multipart form data:

```text
file: string($binary)
```

Accepted formats:

```text
JPEG
PNG
WebP
```

Only `super_admin` can upload or delete package hero images.
