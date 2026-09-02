"""Every error a guest can trigger must arrive as a sentence they can act on.

The frontend prints ``detail`` verbatim, so these tests pin the properties that
make that safe: a 401 says whether to sign in again, a 403 names the role that
would work, a bad query parameter never reaches the 500 handler, and nothing
internal (rate-pair names, provider text, SQL values) leaks into the body.
"""

from datetime import timedelta

import pytest
from httpx import AsyncClient

from app.api.deps import describe_roles
from app.core.security import TokenExpiredError, create_token, decode_token
from app.models.user import UserRole


class TestUnauthenticated:
    async def test_missing_token_says_to_sign_in(self, client: AsyncClient) -> None:
        resp = await client.get("/api/users/me")

        assert resp.status_code == 401
        assert "signed in" in resp.json()["detail"]

    async def test_expired_token_is_told_apart_from_a_bad_one(
        self, client: AsyncClient, customer_user
    ) -> None:
        expired, _ = create_token(
            str(customer_user.id), "access", expires_delta=timedelta(seconds=-10)
        )

        resp = await client.get(
            "/api/users/me", headers={"Authorization": f"Bearer {expired}"}
        )

        assert resp.status_code == 401
        assert "expired" in resp.json()["detail"]

    async def test_garbage_token_asks_for_a_new_session(
        self, client: AsyncClient
    ) -> None:
        resp = await client.get(
            "/api/users/me", headers={"Authorization": "Bearer not.a.jwt"}
        )

        assert resp.status_code == 401
        assert "sign in again" in resp.json()["detail"]

    def test_decode_token_distinguishes_expiry(self, customer_user) -> None:
        expired, _ = create_token(
            str(customer_user.id), "access", expires_delta=timedelta(seconds=-10)
        )

        with pytest.raises(TokenExpiredError):
            decode_token(expired)


class TestForbidden:
    async def test_403_names_the_role_that_would_work(
        self, client: AsyncClient, customer_headers
    ) -> None:
        resp = await client.get("/api/users", headers=customer_headers)

        assert resp.status_code == 403
        detail = resp.json()["detail"]
        assert "platform administrator" in detail
        # Never the bare "Insufficient permissions" the guest cannot act on.
        assert detail != "Insufficient permissions"

    def test_role_phrasing_reads_as_a_sentence(self) -> None:
        assert (
            describe_roles({UserRole.ADMIN, UserRole.SUPER_ADMIN})
            == "a platform administrator or a property administrator"
        )
        assert describe_roles({UserRole.SUPER_ADMIN}) == "a platform administrator"


class TestBadInput:
    @pytest.mark.parametrize("month", ["0000-01", "not-a-month", "2026-13", "2026", ""])
    async def test_bad_month_is_a_400_not_a_500(
        self, client: AsyncClient, month: str
    ) -> None:
        """``0000-01`` matches the YYYY-MM pattern but no real date."""

        resp = await client.get(
            "/api/availability",
            params={
                "sanatorium_id": "00000000-0000-0000-0000-000000000000",
                "month": month,
            },
        )

        assert resp.status_code in (400, 422), resp.text
        assert resp.status_code != 500

    async def test_unreadable_upload_names_the_accepted_formats(
        self, client: AsyncClient, admin_headers, db
    ) -> None:
        from tests.factories import make_sanatorium

        sanatorium = await make_sanatorium(db)
        resp = await client.post(
            f"/api/sanatoriums/{sanatorium.id}/images",
            headers=admin_headers,
            files={"file": ("x.png", b"definitely not a png", "image/png")},
        )

        assert resp.status_code in (403, 415)
        if resp.status_code == 415:
            assert "JPEG" in resp.json()["detail"]


class TestNoInternalLeaks:
    async def test_missing_exchange_rate_does_not_name_the_pair_syntax(self) -> None:
        from app.core.errors import missing_exchange_rate

        exc = missing_exchange_rate("usd", "uzs")

        assert exc.status_code == 503
        assert "USD" in exc.detail and "UZS" in exc.detail
        # Internal pair keys ("USD_UZS") are for the log, not for the guest.
        assert "USD_UZS" not in exc.detail
        assert exc.detail.endswith(".")
