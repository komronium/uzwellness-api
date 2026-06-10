"""Named HTTP error raisers for domain conditions.

One place to define which status code a domain condition maps to, so the
same condition cannot drift between endpoints (e.g. unavailable room being
404 in one flow and 409 in another).
"""

from fastapi import HTTPException, status


def bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def sanatorium_not_bookable() -> HTTPException:
    return bad_request("Sanatorium is not available for booking")


def room_unavailable(
    detail: str = "Selected room is no longer available",
) -> HTTPException:
    return conflict(detail)
