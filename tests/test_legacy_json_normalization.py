from scripts.normalize_legacy_json_shapes import (
    normalize_beds,
    normalize_review_photos,
    normalize_room_features,
)
from app.schemas.room import (
    RoomFeatures,
    normalize_room_features as normalize_room_read_features,
)


def test_normalizes_legacy_room_features():
    result = normalize_room_features(
        {"windows": "all", "bathroom": "private", "balcony": True}
    )

    assert result == {
        "has_window": True,
        "bathroom": {"private": True},
        "comfort": {"balcony": True},
    }


def test_room_read_accepts_legacy_room_features():
    result = RoomFeatures.model_validate(
        normalize_room_read_features(
            {
                "windows": "all",
                "bathroom": "private",
                "balcony": True,
                "sitting_area": True,
            }
        )
    )

    assert result.has_window is True
    assert result.bathroom.private is True
    assert result.comfort.balcony is True
    assert result.comfort.sofa is True


def test_normalizes_legacy_flat_beds():
    result = normalize_beds(
        [
            {"type": "double", "count": 1, "width_cm": 160},
            {"type": "single", "count": 1, "width_cm": 90},
        ]
    )

    assert result == [
        {
            "beds": [
                {"type": "double", "count": 1, "size_cm": "160"},
                {"type": "single", "count": 1, "size_cm": "90"},
            ]
        }
    ]


def test_normalizes_legacy_review_photo_urls():
    result = normalize_review_photos(["/uploads/seed/chortoq/mineral_pool.webp"])

    assert result == [{"url": "/uploads/seed/chortoq/mineral_pool.webp"}]
