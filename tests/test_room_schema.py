import uuid
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from app.models.room import AccommodationType, RoomSizePolicy, SmokingPolicy
from app.schemas.room import RoomRead


def _room_obj(**overrides):
    now = datetime(2026, 1, 1)
    data = {
        "id": uuid.uuid4(),
        "sanatorium_id": uuid.uuid4(),
        "name": {"en": "Standard"},
        "description": {},
        "amenities": [],
        "amenity_links": [],
        "size_sqm": None,
        "room_size_policy": RoomSizePolicy.SAME_SIZE,
        "floor": None,
        "beds": [],
        "view": None,
        "smoking_allowed": False,
        "smoking_policy": SmokingPolicy.NON_SMOKING,
        "window_policy": None,
        "window_description": None,
        "room_features": {},
        "accommodation_type": AccommodationType.HOTEL_ROOM,
        "gender_restriction": None,
        "capacity": 1,
        "max_adults": None,
        "max_children": None,
        "max_child_rate_children": None,
        "inventory_count": 1,
        "room_advisories": [],
        "images": [],
        "base_price": Decimal("100.00"),
        "base_price_weekend": None,
        "base_currency": "USD",
        "markup_percent": Decimal("0"),
        "discount_percent": None,
        "min_nights": 1,
        "is_active": True,
        "display_order": 0,
        "deleted_at": None,
        "created_at": now,
        "updated_at": now,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_room_read_normalizes_legacy_room_features():
    room = _room_obj(
        room_features={"windows": "all", "bathroom": "private", "balcony": True}
    )

    result = RoomRead.from_obj(room, "en")

    assert result.room_features.has_window is True
    assert result.room_features.bathroom.private is True
    assert result.room_features.comfort.balcony is True


def test_room_read_normalizes_legacy_flat_beds():
    room = _room_obj(
        beds=[
            {"type": "double", "count": 1, "width_cm": 160},
            {"type": "single", "count": 1, "width_cm": 90},
        ]
    )

    result = RoomRead.from_obj(room, "en")

    assert len(result.beds) == 1
    assert [bed.type for bed in result.beds[0].beds] == ["double", "single"]
    assert result.beds[0].beds[0].size_cm == "160"
