"""Unit tests for authorization policies (no DB; just stub objects)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest

from app.core.policies import BookingPolicy, ReviewPolicy, SanatoriumPolicy
from app.models.booking import BookingStatus
from app.models.sanatorium import SanatoriumStatus
from app.models.user import UserRole


@dataclass
class _U:
    id: uuid.UUID
    role: UserRole


@dataclass
class _S:
    admin_user_id: uuid.UUID | None
    status: SanatoriumStatus


@dataclass
class _B:
    user_id: uuid.UUID | None
    status: BookingStatus = BookingStatus.CONFIRMED


@dataclass
class _R:
    user_id: uuid.UUID | None


U_SA = _U(uuid.uuid4(), UserRole.SUPER_ADMIN)
U_ADM_OWN = _U(uuid.uuid4(), UserRole.ADMIN)
U_ADM_OTHER = _U(uuid.uuid4(), UserRole.ADMIN)
U_CUST = _U(uuid.uuid4(), UserRole.CUSTOMER)


class TestSanatoriumPolicy:
    def test_anonymous_sees_approved(self):
        s = _S(admin_user_id=None, status=SanatoriumStatus.APPROVED)
        assert SanatoriumPolicy.can_view(s, None) is True

    def test_anonymous_cannot_see_pending(self):
        s = _S(admin_user_id=None, status=SanatoriumStatus.PENDING)
        assert SanatoriumPolicy.can_view(s, None) is False

    def test_super_admin_sees_pending(self):
        s = _S(admin_user_id=None, status=SanatoriumStatus.PENDING)
        assert SanatoriumPolicy.can_view(s, U_SA) is True

    def test_admin_sees_own_pending(self):
        s = _S(admin_user_id=U_ADM_OWN.id, status=SanatoriumStatus.PENDING)
        assert SanatoriumPolicy.can_view(s, U_ADM_OWN) is True

    def test_admin_cannot_see_others_pending(self):
        s = _S(admin_user_id=U_ADM_OTHER.id, status=SanatoriumStatus.PENDING)
        assert SanatoriumPolicy.can_view(s, U_ADM_OWN) is False

    def test_admin_sees_others_approved(self):
        s = _S(admin_user_id=U_ADM_OTHER.id, status=SanatoriumStatus.APPROVED)
        assert SanatoriumPolicy.can_view(s, U_ADM_OWN) is True

    def test_customer_cannot_see_pending(self):
        s = _S(admin_user_id=None, status=SanatoriumStatus.PENDING)
        assert SanatoriumPolicy.can_view(s, U_CUST) is False

    def test_super_admin_can_edit_anything(self):
        s = _S(admin_user_id=None, status=SanatoriumStatus.PENDING)
        assert SanatoriumPolicy.can_edit(s, U_SA) is True

    def test_admin_edits_own(self):
        s = _S(admin_user_id=U_ADM_OWN.id, status=SanatoriumStatus.APPROVED)
        assert SanatoriumPolicy.can_edit(s, U_ADM_OWN) is True

    def test_admin_cannot_edit_others(self):
        s = _S(admin_user_id=U_ADM_OTHER.id, status=SanatoriumStatus.APPROVED)
        assert SanatoriumPolicy.can_edit(s, U_ADM_OWN) is False

    def test_customer_cannot_edit(self):
        s = _S(admin_user_id=None, status=SanatoriumStatus.APPROVED)
        assert SanatoriumPolicy.can_edit(s, U_CUST) is False


class TestBookingPolicy:
    def test_customer_cancels_own(self):
        b = _B(user_id=U_CUST.id, status=BookingStatus.CONFIRMED)
        assert BookingPolicy.can_cancel(b, U_CUST) is True

    def test_customer_cannot_cancel_others(self):
        other = _U(uuid.uuid4(), UserRole.CUSTOMER)
        b = _B(user_id=other.id, status=BookingStatus.CONFIRMED)
        assert BookingPolicy.can_cancel(b, U_CUST) is False

    def test_admin_can_cancel_only_own_sanatorium(self):
        b = _B(user_id=U_CUST.id, status=BookingStatus.CONFIRMED)
        # Admin without ownership context can't cancel — fail-closed default.
        assert BookingPolicy.can_cancel(b, U_ADM_OWN) is False
        # With ownership confirmed by caller, admin can cancel.
        assert BookingPolicy.can_cancel(b, U_ADM_OWN, admin_owns_target=True) is True

    def test_admin_cannot_cancel_other_sanatorium(self):
        b = _B(user_id=U_CUST.id, status=BookingStatus.CONFIRMED)
        reason = BookingPolicy.cancel_block_reason(
            b, U_ADM_OWN, admin_owns_target=False
        )
        assert reason == "Not allowed to cancel this booking"

    def test_super_admin_can_cancel_any(self):
        b = _B(user_id=U_CUST.id, status=BookingStatus.CONFIRMED)
        assert BookingPolicy.can_cancel(b, U_SA) is True

    @pytest.mark.parametrize(
        "status", [BookingStatus.CANCELLED, BookingStatus.COMPLETED]
    )
    def test_terminal_status_blocks_cancel(self, status):
        b = _B(user_id=U_CUST.id, status=status)
        assert BookingPolicy.can_cancel(b, U_CUST) is False
        assert BookingPolicy.can_cancel(b, U_SA) is False

    def test_pending_can_be_cancelled(self):
        b = _B(user_id=U_CUST.id, status=BookingStatus.PENDING)
        assert BookingPolicy.can_cancel(b, U_CUST) is True

    def test_cancel_block_reason_terminal(self):
        b = _B(user_id=U_CUST.id, status=BookingStatus.CANCELLED)
        reason = BookingPolicy.cancel_block_reason(b, U_CUST)
        assert reason is not None
        assert "cancelled" in reason.lower() or "cancel" in reason.lower()

    def test_cancel_block_reason_not_owner(self):
        other = _U(uuid.uuid4(), UserRole.CUSTOMER)
        b = _B(user_id=other.id, status=BookingStatus.CONFIRMED)
        reason = BookingPolicy.cancel_block_reason(b, U_CUST)
        assert reason == "Not allowed to cancel this booking"

    def test_cancel_block_reason_allowed_returns_none(self):
        b = _B(user_id=U_CUST.id, status=BookingStatus.CONFIRMED)
        assert BookingPolicy.cancel_block_reason(b, U_CUST) is None


class TestReviewPolicy:
    def test_super_admin_can_moderate(self):
        r = _R(user_id=U_CUST.id)
        s = _S(admin_user_id=None, status=SanatoriumStatus.APPROVED)
        assert ReviewPolicy.can_moderate(r, U_SA, s) is True

    def test_admin_can_moderate_own_property(self):
        r = _R(user_id=U_CUST.id)
        s = _S(admin_user_id=U_ADM_OWN.id, status=SanatoriumStatus.APPROVED)
        assert ReviewPolicy.can_moderate(r, U_ADM_OWN, s) is True

    def test_admin_cannot_moderate_others_property(self):
        r = _R(user_id=U_CUST.id)
        s = _S(admin_user_id=U_ADM_OTHER.id, status=SanatoriumStatus.APPROVED)
        assert ReviewPolicy.can_moderate(r, U_ADM_OWN, s) is False

    def test_customer_cannot_moderate(self):
        r = _R(user_id=U_CUST.id)
        s = _S(admin_user_id=None, status=SanatoriumStatus.APPROVED)
        assert ReviewPolicy.can_moderate(r, U_CUST, s) is False

    def test_review_author_can_delete_own(self):
        r = _R(user_id=U_CUST.id)
        s = _S(admin_user_id=U_ADM_OTHER.id, status=SanatoriumStatus.APPROVED)
        assert ReviewPolicy.can_delete(r, U_CUST, s) is True

    def test_customer_cannot_delete_others(self):
        other = _U(uuid.uuid4(), UserRole.CUSTOMER)
        r = _R(user_id=other.id)
        s = _S(admin_user_id=U_ADM_OTHER.id, status=SanatoriumStatus.APPROVED)
        assert ReviewPolicy.can_delete(r, U_CUST, s) is False
