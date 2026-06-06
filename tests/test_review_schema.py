import uuid
from datetime import datetime
from types import SimpleNamespace

from app.models.review import ReviewAppealStatus, ReviewReplyStatus, ReviewSource
from app.schemas.review import ReviewRead


def _review_obj(**overrides):
    now = datetime(2026, 1, 1)
    data = {
        "id": uuid.uuid4(),
        "sanatorium_id": uuid.uuid4(),
        "user_id": None,
        "booking_id": None,
        "room_id": None,
        "source": ReviewSource.UZWELLNESS,
        "external_id": None,
        "external_url": None,
        "reviewer_name": "Guest",
        "reviewer_country": None,
        "reviewer_avatar_url": None,
        "traveler_type": None,
        "language": None,
        "stayed_at": None,
        "stayed_room_name": None,
        "rating": 5,
        "score_label": None,
        "cleanliness": None,
        "amenities": None,
        "location": None,
        "service": None,
        "treatment": None,
        "value": None,
        "food": None,
        "body": "A useful review body.",
        "translated_body": None,
        "positive_tags": [],
        "negative_tags": [],
        "photos": [],
        "reply_body": None,
        "reply_language": None,
        "reply_status": ReviewReplyStatus.AWAITING_REPLY,
        "replied_at": None,
        "replied_by_user_id": None,
        "appeal_status": ReviewAppealStatus.NONE,
        "appeal_reason": None,
        "appealed_at": None,
        "is_visible": True,
        "created_at": now,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_review_read_normalizes_legacy_photo_urls():
    review = _review_obj(photos=["/uploads/seed/chortoq/mineral_pool.webp"])

    result = ReviewRead.model_validate(review)

    assert result.photos == [{"url": "/uploads/seed/chortoq/mineral_pool.webp"}]
