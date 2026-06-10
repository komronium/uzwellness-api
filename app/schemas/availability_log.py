import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.models.availability_log import AvailabilityLogCategory
from app.schemas.common import Page


class AvailabilityOperationLogRead(BaseModel):
    id: uuid.UUID
    sanatorium_id: uuid.UUID
    room_id: uuid.UUID | None
    rate_plan_id: uuid.UUID | None
    operated_by_id: uuid.UUID | None
    operated_by_email: str | None
    category: AvailabilityLogCategory
    action: str
    source: str
    check_in_from: date | None
    check_in_to: date | None
    weekdays: list[int]
    before: dict
    after: dict
    details: dict
    created_at: datetime

    @classmethod
    def from_obj(cls, obj) -> "AvailabilityOperationLogRead":
        return cls(
            id=obj.id,
            sanatorium_id=obj.sanatorium_id,
            room_id=obj.room_id,
            rate_plan_id=obj.rate_plan_id,
            operated_by_id=obj.operated_by_id,
            operated_by_email=obj.operated_by.email if obj.operated_by else None,
            category=obj.category,
            action=obj.action,
            source=obj.source,
            check_in_from=obj.check_in_from,
            check_in_to=obj.check_in_to,
            weekdays=obj.weekdays,
            before=obj.before,
            after=obj.after,
            details=obj.details,
            created_at=obj.created_at,
        )


class AvailabilityOperationLogList(Page[AvailabilityOperationLogRead]):
    pass
