"""Unit tests for payment-gateway strategies (no DB)."""

from __future__ import annotations

import base64
import hashlib
from decimal import Decimal

import pytest

from app.core.config import settings
from app.integrations.payment_gateways import (
    CashGateway,
    ClickGateway,
    PaymeGateway,
    get_gateway,
)
from app.models.payment import PaymentMethod


@pytest.fixture(autouse=True)
def restore_settings():
    saved = (
        settings.PAYME_MERCHANT_ID,
        settings.PAYME_MERCHANT_KEY,
        settings.CLICK_SERVICE_ID,
        settings.CLICK_MERCHANT_ID,
        settings.CLICK_SECRET_KEY,
    )
    yield
    (
        settings.PAYME_MERCHANT_ID,
        settings.PAYME_MERCHANT_KEY,
        settings.CLICK_SERVICE_ID,
        settings.CLICK_MERCHANT_ID,
        settings.CLICK_SECRET_KEY,
    ) = saved


class TestRegistry:
    def test_get_each_method_returns_matching_gateway(self):
        assert isinstance(get_gateway(PaymentMethod.PAYME), PaymeGateway)
        assert isinstance(get_gateway(PaymentMethod.CLICK), ClickGateway)
        assert isinstance(get_gateway(PaymentMethod.CASH), CashGateway)


class TestPaymeGateway:
    def test_build_url_without_merchant_id_fallback(self):
        settings.PAYME_MERCHANT_ID = ""
        gw = PaymeGateway()
        url = gw.build_checkout_url(
            amount=Decimal("100"), currency="UZS", merchant_trans_id="abc123"
        )
        assert url is not None
        assert "abc123" in url

    def test_build_url_with_merchant_id_base64_payload(self):
        settings.PAYME_MERCHANT_ID = "my_merchant"
        gw = PaymeGateway()
        url = gw.build_checkout_url(
            amount=Decimal("100"), currency="UZS", merchant_trans_id="abc123"
        )
        assert url is not None
        encoded = url.rsplit("/", 1)[-1].split("?")[0]
        decoded = base64.b64decode(encoded).decode("utf-8")
        assert "m=my_merchant" in decoded
        assert "ac.order_id=abc123" in decoded
        # Payme expects tiyins (×100): 100 UZS = 10000 tiyin
        assert "a=10000" in decoded

    def test_verify_webhook_rejects_when_no_secret(self):
        settings.PAYME_MERCHANT_KEY = ""
        gw = PaymeGateway()
        assert gw.verify_webhook(payload={}, headers={}) is False

    def test_verify_webhook_accepts_correct_basic_auth(self):
        settings.PAYME_MERCHANT_KEY = "topsecret"
        gw = PaymeGateway()
        token = base64.b64encode(b"Paycom:topsecret").decode("ascii")
        headers = {"Authorization": f"Basic {token}"}
        assert gw.verify_webhook(payload={}, headers=headers) is True

    def test_verify_webhook_rejects_wrong_secret(self):
        settings.PAYME_MERCHANT_KEY = "topsecret"
        gw = PaymeGateway()
        token = base64.b64encode(b"Paycom:wrong").decode("ascii")
        headers = {"Authorization": f"Basic {token}"}
        assert gw.verify_webhook(payload={}, headers=headers) is False

    def test_verify_webhook_rejects_missing_header(self):
        settings.PAYME_MERCHANT_KEY = "topsecret"
        gw = PaymeGateway()
        assert gw.verify_webhook(payload={}, headers={}) is False

    def test_parse_webhook_extracts_order_id(self):
        gw = PaymeGateway()
        result = gw.parse_webhook(
            payload={
                "params": {
                    "account": {"order_id": "order-xyz"},
                    "id": "payme-payment-1",
                }
            }
        )
        assert result.merchant_trans_id == "order-xyz"
        assert result.provider_payment_id == "payme-payment-1"
        assert result.is_paid is True
        assert result.is_failed is False

    def test_parse_webhook_missing_id_raises(self):
        gw = PaymeGateway()
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            gw.parse_webhook(payload={"params": {}})
        assert exc.value.status_code == 400


class TestClickGateway:
    def test_build_url_without_service_id_fallback(self):
        settings.CLICK_SERVICE_ID = ""
        gw = ClickGateway()
        url = gw.build_checkout_url(
            amount=Decimal("100"), currency="UZS", merchant_trans_id="abc"
        )
        assert url is not None
        assert "abc" in url

    def test_build_url_with_service_id_query_params(self):
        settings.CLICK_SERVICE_ID = "svc1"
        settings.CLICK_MERCHANT_ID = "merch1"
        gw = ClickGateway()
        url = gw.build_checkout_url(
            amount=Decimal("250.50"), currency="UZS", merchant_trans_id="abc"
        )
        assert url is not None
        assert "service_id=svc1" in url
        assert "merchant_id=merch1" in url
        assert "amount=250.50" in url
        assert "transaction_param=abc" in url

    def test_verify_webhook_rejects_when_no_secret(self):
        settings.CLICK_SECRET_KEY = ""
        gw = ClickGateway()
        assert (
            gw.verify_webhook(payload={"sign_string": "anything"}, headers={}) is False
        )

    def test_verify_webhook_rejects_missing_signature(self):
        settings.CLICK_SECRET_KEY = "secret"
        gw = ClickGateway()
        assert gw.verify_webhook(payload={}, headers={}) is False

    def test_verify_webhook_accepts_correct_signature(self):
        settings.CLICK_SECRET_KEY = "secret"
        gw = ClickGateway()
        payload = {
            "click_trans_id": "1",
            "service_id": "svc",
            "merchant_trans_id": "mt1",
            "amount": "100",
            "action": "1",
            "sign_time": "2026-01-01 00:00:00",
        }
        # Construct expected MD5 the same way the gateway does
        parts = ["1", "svc", "secret", "mt1", "100", "1", "2026-01-01 00:00:00"]
        expected = hashlib.md5(
            "".join(parts).encode(), usedforsecurity=False
        ).hexdigest()
        payload["sign_string"] = expected
        assert gw.verify_webhook(payload=payload, headers={}) is True

    def test_verify_webhook_rejects_wrong_signature(self):
        settings.CLICK_SECRET_KEY = "secret"
        gw = ClickGateway()
        payload = {
            "click_trans_id": "1",
            "service_id": "svc",
            "merchant_trans_id": "mt1",
            "amount": "100",
            "action": "1",
            "sign_time": "now",
            "sign_string": "deadbeef",
        }
        assert gw.verify_webhook(payload=payload, headers={}) is False

    def test_parse_webhook_success(self):
        gw = ClickGateway()
        result = gw.parse_webhook(
            payload={
                "merchant_trans_id": "abc",
                "click_trans_id": "click-999",
                "action": 1,
                "error": 0,
            }
        )
        assert result.merchant_trans_id == "abc"
        assert result.provider_payment_id == "click-999"
        assert result.is_paid is True
        assert result.is_failed is False

    def test_parse_webhook_failure(self):
        gw = ClickGateway()
        result = gw.parse_webhook(
            payload={
                "merchant_trans_id": "abc",
                "action": 1,
                "error": -1,
            }
        )
        assert result.is_paid is False
        assert result.is_failed is True

    def test_parse_webhook_missing_id_raises(self):
        gw = ClickGateway()
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            gw.parse_webhook(payload={})
        assert exc.value.status_code == 400


class TestCashGateway:
    def test_build_url_returns_none(self):
        gw = CashGateway()
        assert (
            gw.build_checkout_url(
                amount=Decimal("100"), currency="UZS", merchant_trans_id="abc"
            )
            is None
        )

    def test_verify_webhook_false(self):
        assert CashGateway().verify_webhook(payload={}, headers={}) is False

    def test_parse_webhook_raises(self):
        with pytest.raises(NotImplementedError):
            CashGateway().parse_webhook(payload={})
