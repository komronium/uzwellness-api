"""Centralised authorization policies. Each policy answers one yes/no question.

Services and routers ask a Policy "can this user do X to this resource?" instead
of inlining role checks. Adds clarity and a single source of truth for rules.
"""

from __future__ import annotations

from app.models.booking import Booking, BookingStatus
from app.models.review import SanatoriumReview
from app.models.sanatorium import Sanatorium, SanatoriumStatus
from app.models.user import User, UserRole

_CANCELLABLE = {BookingStatus.PENDING, BookingStatus.CONFIRMED}


class SanatoriumPolicy:
    @staticmethod
    def can_view(sanatorium: Sanatorium, user: User | None) -> bool:
        if user is not None and user.role == UserRole.SUPER_ADMIN:
            return True
        if (
            user is not None
            and user.role == UserRole.ADMIN
            and sanatorium.admin_user_id == user.id
        ):
            return True
        return sanatorium.status == SanatoriumStatus.APPROVED

    @staticmethod
    def can_edit(sanatorium: Sanatorium, user: User) -> bool:
        if user.role == UserRole.SUPER_ADMIN:
            return True
        return user.role == UserRole.ADMIN and sanatorium.admin_user_id == user.id


class BookingPolicy:
    @staticmethod
    def can_cancel(
        booking: Booking, user: User, *, admin_owns_target: bool = False
    ) -> bool:
        if booking.status not in _CANCELLABLE:
            return False
        if user.role == UserRole.SUPER_ADMIN:
            return True
        if user.role == UserRole.ADMIN:
            return admin_owns_target
        return booking.user_id == user.id

    @staticmethod
    def cancel_block_reason(
        booking: Booking, user: User, *, admin_owns_target: bool = False
    ) -> str | None:
        if booking.status not in _CANCELLABLE:
            return f"Booking cannot be cancelled (status: {booking.status})"
        if user.role == UserRole.SUPER_ADMIN:
            return None
        if user.role == UserRole.ADMIN:
            return None if admin_owns_target else "Not allowed to cancel this booking"
        if booking.user_id != user.id:
            return "Not allowed to cancel this booking"
        return None


class ReviewPolicy:
    @staticmethod
    def can_moderate(
        review: SanatoriumReview, user: User, sanatorium: Sanatorium | None
    ) -> bool:
        if user.role == UserRole.SUPER_ADMIN:
            return True
        if user.role == UserRole.ADMIN and sanatorium is not None:
            return sanatorium.admin_user_id == user.id
        return False

    @staticmethod
    def can_delete(
        review: SanatoriumReview, user: User, sanatorium: Sanatorium | None
    ) -> bool:
        if ReviewPolicy.can_moderate(review, user, sanatorium):
            return True
        return review.user_id == user.id
