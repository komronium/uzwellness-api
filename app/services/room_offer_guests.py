"""Guest composition and treatment-program matching for room-offer search.

Pure functions: who is staying in each requested room, which board/treatment
choice applies to each guest, and which stay-package programs a guest may
select. Used by both offer pricing and offer presentation.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.program import (
    TreatmentGuestApplicability,
    TreatmentProgram,
    TreatmentStayPackageKind,
)
from app.models.rate_plan import BoardType
from app.schemas.room_offer import (
    RoomOfferGuest,
    RoomOfferGuestType,
    RoomOfferPackageKind,
    RoomOfferRequestedRoom,
    RoomOfferSearchRequest,
)

GuestKey = tuple[int, int]
"""(room_index, guest_index)"""


@dataclass(slots=True)
class GuestStayChoice:
    room_index: int
    guest_index: int
    board: BoardType
    treatment_included: bool

    @property
    def package_kind(self) -> RoomOfferPackageKind:
        return (
            RoomOfferPackageKind.TREATMENT
            if self.treatment_included
            else RoomOfferPackageKind.SPECIAL
        )


def guests(requested_room: RoomOfferRequestedRoom) -> list[RoomOfferGuest]:
    result = [
        RoomOfferGuest(guest_index=index, type=RoomOfferGuestType.ADULT)
        for index in range(requested_room.adults)
    ]
    offset = requested_room.adults
    result.extend(
        RoomOfferGuest(
            guest_index=offset + index,
            type=RoomOfferGuestType.CHILD,
            age=child.age,
        )
        for index, child in enumerate(requested_room.children)
    )
    return result


def default_guest_option(
    room_index: int,
    guest_index: int,
    *,
    board: BoardType = BoardType.FULL_BOARD,
) -> GuestStayChoice:
    return GuestStayChoice(
        room_index=room_index,
        guest_index=guest_index,
        board=board,
        treatment_included=True,
    )


def guest_options(payload: RoomOfferSearchRequest) -> dict[GuestKey, GuestStayChoice]:
    room_boards = {
        room_index: room.board for room_index, room in enumerate(payload.rooms)
    }
    options: dict[GuestKey, GuestStayChoice] = {}
    for item in payload.guest_options:
        if item.room_index >= len(payload.rooms):
            continue
        if item.guest_index >= payload.rooms[item.room_index].guests_count:
            continue
        options[(item.room_index, item.guest_index)] = GuestStayChoice(
            room_index=item.room_index,
            guest_index=item.guest_index,
            board=item.board or room_boards[item.room_index],
            treatment_included=item.treatment_included,
        )
    for room_index, room in enumerate(payload.rooms):
        for guest in guests(room):
            options.setdefault(
                (room_index, guest.guest_index),
                default_guest_option(
                    room_index,
                    guest.guest_index,
                    board=room_boards[room_index],
                ),
            )
    return options


def guest_option(
    options: dict[GuestKey, GuestStayChoice], room_index: int, guest_index: int
) -> GuestStayChoice:
    return options.get(
        (room_index, guest_index), default_guest_option(room_index, guest_index)
    )


def program_kind(option: GuestStayChoice) -> TreatmentStayPackageKind:
    return (
        TreatmentStayPackageKind.TREATMENT
        if option.treatment_included
        else TreatmentStayPackageKind.SPECIAL
    )


def programs_for_guest(
    programs: list[TreatmentProgram],
    guest: RoomOfferGuest,
    package_kind: TreatmentStayPackageKind,
) -> list[TreatmentProgram]:
    if guest.type == RoomOfferGuestType.ADULT:
        allowed = {
            TreatmentGuestApplicability.ALL,
            TreatmentGuestApplicability.ADULT,
        }
    else:
        allowed = {
            TreatmentGuestApplicability.ALL,
            TreatmentGuestApplicability.CHILD,
        }
    return [
        program
        for program in programs
        if program.guest_applicability in allowed
        and program.stay_package_kind == package_kind
    ]


def resolve_guest_program(
    treatments: list[TreatmentProgram],
    treatment_by_guest: dict[GuestKey, TreatmentProgram],
    room_index: int,
    guest: RoomOfferGuest,
    option: GuestStayChoice,
) -> TreatmentProgram | None:
    """The guest's explicitly selected program, or their default (first match)."""
    programs = programs_for_guest(treatments, guest, program_kind(option))
    default = programs[0] if programs else None
    return treatment_by_guest.get((room_index, guest.guest_index), default)


def selected_treatments(
    payload: RoomOfferSearchRequest,
    treatments: list[TreatmentProgram],
    options: dict[GuestKey, GuestStayChoice],
) -> dict[GuestKey, TreatmentProgram]:
    """Validated explicit program selections; invalid items are dropped."""
    by_id = {program.id: program for program in treatments}
    selected: dict[GuestKey, TreatmentProgram] = {}
    for item in payload.treatment_selections:
        program = by_id.get(item.program_id)
        if program is None:
            continue
        if item.room_index >= len(payload.rooms):
            continue
        if item.guest_index >= payload.rooms[item.room_index].guests_count:
            continue
        guest = guests(payload.rooms[item.room_index])[item.guest_index]
        option = guest_option(options, item.room_index, item.guest_index)
        if program not in programs_for_guest([program], guest, program_kind(option)):
            continue
        selected[(item.room_index, item.guest_index)] = program
    return selected
