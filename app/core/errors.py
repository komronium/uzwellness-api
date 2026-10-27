"""Named HTTP error raisers for domain conditions.

One place to define which status code a domain condition maps to, so the
same condition cannot drift between endpoints (e.g. unavailable room being
404 in one flow and 409 in another).
"""

from datetime import date

from fastapi import HTTPException, status

from app.core.utils import today_tashkent

# Session wording lives here so the token check in app/api/deps.py and the
# refresh endpoint in auth_service answer with the same sentence — a guest who
# sees two different explanations for one expired login files a support ticket.
SIGN_IN_REQUIRED = "You must be signed in to do this. Please log in and try again."
SESSION_EXPIRED = "Your session has expired. Please sign in again."
SESSION_INVALID = "Your session is no longer valid. Please sign in again."
ACCOUNT_DISABLED = "This account has been disabled. Please contact info@uzwellness.com."


PAST_CHECK_IN = "Check-in cannot be in the past. Please pick today or a later date."


def bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def sanatorium_not_bookable() -> HTTPException:
    """A property that exists but is not approved, or does not exist at all.

    The two cases share one message on purpose: an unapproved property is not
    public yet, and a distinct "not found" would confirm which ids are taken.
    """

    return bad_request(
        "This property is not open for online booking yet. "
        "Please choose another property or contact us to book by phone."
    )


def ensure_check_in_not_past(check_in: date) -> None:
    """Searches and bookings share this cutoff (Tashkent "today").

    A search that priced a past stay would show offers the guest can never book.
    """

    if check_in < today_tashkent():
        raise bad_request(PAST_CHECK_IN)


def room_unavailable(
    detail: str = (
        "This room is no longer available for the dates you selected. "
        "Please pick different dates or another room."
    ),
) -> HTTPException:
    return conflict(detail)


def missing_exchange_rate(source: str, target: str) -> HTTPException:
    """No stored rate for a conversion the price depends on.

    This is our configuration failing, not the caller's request, so it answers
    503 (retry later) rather than 400 (fix your input) — and it names the pair
    so support can act on a screenshot without opening the logs.
    """

    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            f"Prices cannot be converted from {source.upper()} to "
            f"{target.upper()} right now because that exchange rate is not "
            "available. Please try again shortly or contact us to book by phone."
        ),
    )
