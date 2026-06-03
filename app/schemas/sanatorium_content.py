import uuid
from decimal import Decimal

from pydantic import BaseModel, Field


class ContentTask(BaseModel):
    code: str
    title: str
    section: str
    score_delta_percent: int = Field(ge=1, le=100)
    is_complete: bool
    target_url: str | None = None


class ContentSection(BaseModel):
    code: str
    title: str
    is_complete: bool
    completed_items: int
    total_items: int


class CompetitiveSetRankItem(BaseModel):
    sanatorium_id: uuid.UUID
    name: str
    score_percent: int
    rank: int


class SanatoriumContentOverview(BaseModel):
    sanatorium_id: uuid.UUID
    score_percent: int
    excludes_some_room_types: bool
    sections: list[ContentSection]
    tasks: list[ContentTask]
    competitive_set_ranking: list[CompetitiveSetRankItem] = Field(default_factory=list)
    property_rooms_count: int
    total_inventory_count: int
    avg_rating: Decimal | None
