import uuid

from fastapi import Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import assert_sanatorium_access
from app.core.utils import pick_locale
from app.models.amenity import SanatoriumAmenity
from app.models.room import Room, RoomImage
from app.models.sanatorium import Sanatorium, SanatoriumImage
from app.models.user import User
from app.schemas.sanatorium_content import (
    CompetitiveSetRankItem,
    ContentSection,
    ContentTask,
    SanatoriumContentOverview,
)


class SanatoriumContentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def overview(
        self, sanatorium: Sanatorium, user: User, *, locale: str
    ) -> SanatoriumContentOverview:
        await assert_sanatorium_access(
            self.db, sanatorium.id, user, action="view property content overview"
        )
        facts = await self._facts(sanatorium.id)
        sections = _sections(sanatorium, facts)
        tasks = _tasks(sanatorium, facts)
        completed = sum(section.completed_items for section in sections)
        total = sum(section.total_items for section in sections) or 1
        score = round(completed / total * 100)
        return SanatoriumContentOverview(
            sanatorium_id=sanatorium.id,
            score_percent=score,
            excludes_some_room_types=facts["rooms_missing_core_info"] > 0,
            sections=sections,
            tasks=tasks,
            competitive_set_ranking=await self._competitive_set(
                sanatorium, score, locale=locale
            ),
            property_rooms_count=facts["room_types_count"],
            total_inventory_count=facts["total_inventory"],
            avg_rating=sanatorium.avg_rating,
        )

    async def _facts(self, sanatorium_id: uuid.UUID) -> dict[str, int]:
        room_rows = (
            await self.db.execute(
                select(
                    func.count(Room.id),
                    func.coalesce(func.sum(Room.inventory_count), 0),
                    func.sum(
                        case(
                            (
                                (Room.size_sqm.is_(None))
                                | (Room.view.is_(None))
                                | (Room.window_policy.is_(None))
                                | (Room.smoking_policy.is_(None))
                                | (Room.beds == [])
                                | (Room.room_features == {}),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                ).where(Room.sanatorium_id == sanatorium_id, Room.deleted_at.is_(None))
            )
        ).one()
        room_images = await self.db.scalar(
            select(func.count(RoomImage.id))
            .join(Room, RoomImage.room_id == Room.id)
            .where(Room.sanatorium_id == sanatorium_id, Room.deleted_at.is_(None))
        )
        property_images = await self.db.scalar(
            select(func.count(SanatoriumImage.id)).where(
                SanatoriumImage.sanatorium_id == sanatorium_id
            )
        )
        amenities = await self.db.scalar(
            select(func.count(SanatoriumAmenity.amenity_id)).where(
                SanatoriumAmenity.sanatorium_id == sanatorium_id,
                SanatoriumAmenity.is_available.is_(True),
            )
        )
        room_types, total_inventory, rooms_missing_core_info = room_rows
        return {
            "room_types_count": int(room_types or 0),
            "total_inventory": int(total_inventory or 0),
            "rooms_missing_core_info": int(rooms_missing_core_info or 0),
            "room_images_count": int(room_images or 0),
            "property_images_count": int(property_images or 0),
            "amenities_count": int(amenities or 0),
        }

    async def _competitive_set(
        self, sanatorium: Sanatorium, score: int, *, locale: str
    ) -> list[CompetitiveSetRankItem]:
        rows = (
            await self.db.scalars(
                select(Sanatorium)
                .where(
                    Sanatorium.id != sanatorium.id,
                    Sanatorium.city == sanatorium.city,
                )
                .order_by(Sanatorium.avg_rating.desc().nullslast())
                .limit(3)
            )
        ).all()
        items = [
            CompetitiveSetRankItem(
                sanatorium_id=item.id,
                name=pick_locale(item.name, locale),
                score_percent=0,
                rank=index,
            )
            for index, item in enumerate(rows, start=1)
        ]
        items.append(
            CompetitiveSetRankItem(
                sanatorium_id=sanatorium.id,
                name=pick_locale(sanatorium.name, locale),
                score_percent=score,
                rank=len(items) + 1,
            )
        )
        return items


def _sections(sanatorium: Sanatorium, facts: dict[str, int]) -> list[ContentSection]:
    checks = [
        (
            "general_information",
            "General Information",
            [
                bool(sanatorium.name),
                bool(sanatorium.description),
                bool(sanatorium.address),
                bool(sanatorium.phones),
                bool(sanatorium.customer_support_email),
                sanatorium.lat is not None and sanatorium.lng is not None,
                sanatorium.year_opened is not None,
                sanatorium.host_type is not None,
            ],
        ),
        (
            "photos_videos",
            "Photos & Videos",
            [
                facts["property_images_count"] >= 5,
                facts["room_images_count"] >= facts["room_types_count"],
            ],
        ),
        (
            "room_information",
            "Room Information",
            [
                facts["room_types_count"] > 0,
                facts["rooms_missing_core_info"] == 0,
            ],
        ),
        (
            "facilities_services",
            "Facilities & Services",
            [facts["amenities_count"] >= 3],
        ),
        ("property_highlights", "Property Highlights", [bool(sanatorium.highlights)]),
    ]
    return [
        ContentSection(
            code=code,
            title=title,
            completed_items=sum(1 for item in items if item),
            total_items=len(items),
            is_complete=all(items),
        )
        for code, title, items in checks
    ]


def _tasks(sanatorium: Sanatorium, facts: dict[str, int]) -> list[ContentTask]:
    tasks: list[ContentTask] = []
    if facts["rooms_missing_core_info"] > 0:
        tasks.append(
            ContentTask(
                code="update_room_core_info",
                title="Update room size, beds, view, window, and smoking policy for room types.",
                section="room_information",
                score_delta_percent=3,
                is_complete=False,
            )
        )
    if facts["amenities_count"] < 3:
        tasks.append(
            ContentTask(
                code="add_facilities",
                title="Please update info on at least 3 more facilities that guests care about.",
                section="facilities_services",
                score_delta_percent=2,
                is_complete=False,
            )
        )
    if facts["room_images_count"] < facts["room_types_count"]:
        tasks.append(
            ContentTask(
                code="add_room_photos",
                title="Provide photos for some room types.",
                section="photos_videos",
                score_delta_percent=1,
                is_complete=False,
            )
        )
    if not sanatorium.highlights:
        tasks.append(
            ContentTask(
                code="add_property_highlights",
                title="Make your property stand out by adding highlights.",
                section="property_highlights",
                score_delta_percent=2,
                is_complete=False,
            )
        )
    return tasks


def get_sanatorium_content_service(
    db: AsyncSession = Depends(get_db),
) -> SanatoriumContentService:
    return SanatoriumContentService(db)
