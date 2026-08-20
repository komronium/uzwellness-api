from fastapi import HTTPException, status

from app.core.utils import pick_locale
from app.models.amenity import Amenity, AmenityScope


def assert_amenity_scope(
    amenities: list[Amenity],
    *,
    allowed: set[AmenityScope],
    resource: str,
) -> None:
    """Reject amenities the catalogue does not offer for ``resource``.

    The catalogue mixes property-level entries ("Parking", "Massage") with
    room-level ones, so a picker that lists everything lets an admin tick an
    amenity that cannot be attached here. Naming the offenders turns an opaque
    400 into something the UI can point at.
    """

    invalid = [item for item in amenities if item.scope not in allowed]
    if not invalid:
        return
    names = ", ".join(
        f"{pick_locale(item.name, 'en') or item.id} ({item.scope})" for item in invalid
    )
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            f"These amenities cannot be attached to a {resource}: {names}. "
            f"List selectable ones with GET /amenities?scope={resource}."
        ),
    )
