"""Email-code-verified booking cancellation with admin approval.

Flow:
1. The booking owner requests a code -> a 6-digit code is emailed to them.
2. They confirm the code -> the request moves to ``awaiting_approval`` and the
   property admin is notified. The booking stays active.
3. An admin approves -> the booking is cancelled and the refund is queued
   (via :meth:`BookingService.cancel`), or rejects -> the booking stays active.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.booking import Booking, BookingStatus
from app.models.cancellation import CancellationRequest, CancellationStatus
from app.models.notification import Notification
from app.models.package import Package
from app.models.program import TreatmentProgram
from app.models.room import Room
from app.models.sanatorium import Sanatorium
from app.models.user import User, UserRole
from app.services.booking_service import BookingService, get_booking_service
from app.services.booking_visibility import admin_owns_booking_sanatorium
from app.services.email_service import (
    send_admin_cancellation_request,
    send_cancellation_code,
    send_cancellation_rejected,
)

_ACTIVE = (CancellationStatus.CODE_SENT, CancellationStatus.AWAITING_APPROVAL)


async def active_cancellation_status_map(
    db: AsyncSession, booking_ids: list[uuid.UUID]
) -> dict[uuid.UUID, CancellationStatus]:
    """Latest active cancellation status per booking (for BookingRead)."""
    if not booking_ids:
        return {}
    rows = (
        await db.execute(
            select(CancellationRequest.booking_id, CancellationRequest.status)
            .where(
                CancellationRequest.booking_id.in_(booking_ids),
                CancellationRequest.status.in_(_ACTIVE),
            )
            .order_by(
                CancellationRequest.booking_id,
                CancellationRequest.created_at.desc(),
            )
        )
    ).all()
    result: dict[uuid.UUID, CancellationStatus] = {}
    for booking_id, st in rows:
        result.setdefault(booking_id, st)  # first row per booking = latest
    return result


def _hash_code(code: str) -> str:
    return hmac.new(
        settings.JWT_SECRET_KEY.encode(), code.encode(), hashlib.sha256
    ).hexdigest()


class CancellationService:
    CODE_TTL_MINUTES = 15
    MAX_ATTEMPTS = 5

    def __init__(self, db: AsyncSession, bookings: BookingService) -> None:
        self.db = db
        self.bookings = bookings

    async def request_code(self, booking: Booking, user: User) -> CancellationRequest:
        self._assert_owner(booking, user)
        self._assert_cancellable_status(booking)
        owner = await self.db.get(User, booking.user_id) if booking.user_id else None
        if owner is None or not owner.email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Booking has no email address to send the code to",
            )

        await self._supersede_active(booking.id)
        code = f"{secrets.randbelow(1_000_000):06d}"
        request = CancellationRequest(
            booking_id=booking.id,
            code_hash=_hash_code(code),
            expires_at=datetime.now(UTC) + timedelta(minutes=self.CODE_TTL_MINUTES),
            status=CancellationStatus.CODE_SENT,
            requested_by_id=user.id,
        )
        self.db.add(request)
        await self.db.commit()
        await self.db.refresh(request)

        send_cancellation_code(
            to=owner.email,
            code=code,
            booking_code=booking.code,
            minutes=self.CODE_TTL_MINUTES,
        )
        return request

    async def confirm_code(
        self, booking: Booking, user: User, code: str
    ) -> CancellationRequest:
        self._assert_owner(booking, user)
        request = await self._latest(booking.id, CancellationStatus.CODE_SENT)
        if request is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No pending cancellation request; request a code first",
            )
        now = datetime.now(UTC)
        if request.expires_at <= now:
            request.status = CancellationStatus.EXPIRED
            await self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cancellation code expired; request a new one",
            )
        if request.attempts >= self.MAX_ATTEMPTS:
            request.status = CancellationStatus.EXPIRED
            await self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many attempts; request a new code",
            )
        if not hmac.compare_digest(request.code_hash, _hash_code(code)):
            request.attempts += 1
            await self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid cancellation code",
            )

        request.status = CancellationStatus.AWAITING_APPROVAL
        self.db.add(
            Notification(
                booking_id=booking.id,
                type="cancellation_requested",
                channel="email",
            )
        )
        await self.db.commit()
        await self.db.refresh(request)

        admin_email = await self._sanatorium_admin_email(booking)
        if admin_email:
            send_admin_cancellation_request(
                to=admin_email,
                booking_code=booking.code,
                reservation_number=booking.reservation_number,
            )
        return request

    async def approve(self, booking: Booking, admin: User) -> Booking:
        await self._assert_admin_owns(booking, admin)
        request = await self._latest(booking.id, CancellationStatus.AWAITING_APPROVAL)
        if request is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No cancellation request awaiting approval",
            )
        # Releases inventory, marks payments refund_pending, emails the customer.
        cancelled = await self.bookings.cancel(booking, admin)
        request.status = CancellationStatus.APPROVED
        request.decided_by_id = admin.id
        request.decided_at = datetime.now(UTC)
        await self.db.commit()
        return cancelled

    async def reject(self, booking: Booking, admin: User) -> CancellationRequest:
        await self._assert_admin_owns(booking, admin)
        request = await self._latest(booking.id, CancellationStatus.AWAITING_APPROVAL)
        if request is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No cancellation request awaiting approval",
            )
        request.status = CancellationStatus.REJECTED
        request.decided_by_id = admin.id
        request.decided_at = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(request)

        owner = await self.db.get(User, booking.user_id) if booking.user_id else None
        if owner is not None and owner.email:
            send_cancellation_rejected(to=owner.email, booking_code=booking.code)
        return request

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _assert_owner(booking: Booking, user: User) -> None:
        if booking.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the booking owner can request its cancellation",
            )

    @staticmethod
    def _assert_cancellable_status(booking: Booking) -> None:
        if booking.status not in {BookingStatus.PENDING, BookingStatus.CONFIRMED}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A {booking.status.value} booking cannot be cancelled",
            )

    async def _assert_admin_owns(self, booking: Booking, admin: User) -> None:
        if admin.role == UserRole.SUPER_ADMIN:
            return
        if admin.role == UserRole.ADMIN and await admin_owns_booking_sanatorium(
            self.db, booking, admin.id
        ):
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to decide this cancellation",
        )

    async def _latest(
        self, booking_id: uuid.UUID, status_value: CancellationStatus
    ) -> CancellationRequest | None:
        return await self.db.scalar(
            select(CancellationRequest)
            .where(
                CancellationRequest.booking_id == booking_id,
                CancellationRequest.status == status_value,
            )
            .order_by(CancellationRequest.created_at.desc())
            .limit(1)
            .with_for_update()
        )

    async def _supersede_active(self, booking_id: uuid.UUID) -> None:
        rows = (
            await self.db.scalars(
                select(CancellationRequest)
                .where(
                    CancellationRequest.booking_id == booking_id,
                    CancellationRequest.status.in_(_ACTIVE),
                )
                .with_for_update()
            )
        ).all()
        for row in rows:
            row.status = CancellationStatus.SUPERSEDED

    async def _sanatorium_admin_email(self, booking: Booking) -> str | None:
        sanatorium_id = await self._sanatorium_id(booking)
        if sanatorium_id is None:
            return None
        admin_id = await self.db.scalar(
            select(Sanatorium.admin_user_id).where(Sanatorium.id == sanatorium_id)
        )
        if admin_id is None:
            return None
        return await self.db.scalar(select(User.email).where(User.id == admin_id))

    async def _sanatorium_id(self, booking: Booking) -> uuid.UUID | None:
        if booking.room_id is not None:
            return await self.db.scalar(
                select(Room.sanatorium_id).where(Room.id == booking.room_id)
            )
        if booking.program_id is not None:
            return await self.db.scalar(
                select(TreatmentProgram.sanatorium_id).where(
                    TreatmentProgram.id == booking.program_id
                )
            )
        if booking.package_id is not None:
            return await self.db.scalar(
                select(Package.sanatorium_id).where(Package.id == booking.package_id)
            )
        return None


def get_cancellation_service(
    db: AsyncSession = Depends(get_db),
) -> CancellationService:
    return CancellationService(db, get_booking_service(db))
