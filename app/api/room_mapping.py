from app.core.currency import CurrencyConverter
from app.core.pricing import enrich_room
from app.models.room import Room
from app.schemas.room import RoomAdminRead, RoomRead, RoomSearchResult
from app.services.room_search import RoomSearchHit


def room_public_read(
    room: Room,
    pricing: dict,
    *,
    locale: str,
    has_availability: bool | None = None,
) -> RoomRead:
    if has_availability is None:
        has_availability = room.is_active and room.inventory_count >= 1
    return RoomRead.from_obj(room, locale).model_copy(
        update={**pricing, "has_availability": has_availability}
    )


def room_admin_read(
    room: Room,
    pricing: dict,
    *,
    has_availability: bool | None = None,
) -> RoomAdminRead:
    if has_availability is None:
        has_availability = room.is_active and room.inventory_count >= 1
    return RoomAdminRead.model_validate(room).model_copy(
        update={**pricing, "has_availability": has_availability}
    )


def room_public_list(
    rooms: list[Room],
    *,
    locale: str,
    converter: CurrencyConverter,
    availability: dict,
) -> list[RoomRead]:
    return [
        room_public_read(
            room,
            enrich_room(room, converter),
            locale=locale,
            has_availability=availability.get(room.id, False),
        )
        for room in rooms
    ]


def room_admin_list(
    rooms: list[Room],
    *,
    converter: CurrencyConverter,
    availability: dict,
) -> list[RoomAdminRead]:
    return [
        room_admin_read(
            room,
            enrich_room(room, converter),
            has_availability=availability.get(room.id, False),
        )
        for room in rooms
    ]


def room_search_result(hit: RoomSearchHit, *, locale: str) -> RoomSearchResult:
    base = room_public_read(
        hit.room,
        hit.pricing,
        locale=locale,
        has_availability=hit.room.is_active and hit.room.inventory_count >= 1,
    )
    return RoomSearchResult(
        **base.model_dump(),
        available=hit.available,
        rooms_count_needed=hit.rooms_count_needed,
        unavailable_reason=hit.unavailable_reason,
    )
