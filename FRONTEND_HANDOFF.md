# Frontend Handoff: Featured Sanatoriums

This file contains only the latest frontend-facing backend change.

## Homepage Featured Sanatorium Cards

Use this endpoint for the homepage "Top-rated by international guests" section.

```http
GET /api/sanatoriums/featured
```

It returns approved sanatoriums where `is_featured=true`, ordered by `display_order`, then rating.

Query params:

```text
limit: integer | default 20
offset: integer | default 0
lang: uz | ru | en | optional
```

Response:

```json
{
  "items": [
    {
      "sanatorium_id": "uuid",
      "sanatorium_slug": "zaamin-health-resort",
      "sanatorium_name": "Zaamin Health Resort",
      "city": "Zaamin",
      "region_id": "uuid",
      "region_name": "Jizzakh",
      "destination_id": "uuid",
      "destination_name": "Zaamin National Park",
      "primary_image_url": "/uploads/sanatoriums/zaamin.jpg",
      "photos_count": 12,
      "stars": 4,
      "avg_rating": "4.80",
      "review_count": 42,
      "property_type": "sanatorium",
      "wellness_category": null,
      "treatment_focuses": ["respiratory", "wellness"],
      "min_price": "1000000.00",
      "min_price_currency": "UZS",
      "min_price_usd": "80.00",
      "is_featured": true,
      "display_order": 1
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

Rules:

- Public endpoint returns only approved featured sanatoriums.
- `primary_image_url` uses the primary sanatorium image, otherwise the first image.
- `photos_count` is the number of sanatorium images.
- `min_price` is calculated from active rooms with positive inventory.
- `min_price_usd` uses `USD_UZS` exchange rate when room currency is `UZS`.
- `is_featured` and `display_order` are backend/admin controls.
