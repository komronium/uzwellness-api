import base64

import app.services.email_service as es


def test_send_resend_posts_with_base64_attachment(monkeypatch) -> None:
    captured: dict = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(url=url, headers=headers, json=json)
        return FakeResponse()

    monkeypatch.setattr(es.settings, "RESEND_API_KEY", "re_test_key")
    monkeypatch.setattr(es.settings, "EMAIL_FROM", "info@uzwellness.com")
    monkeypatch.setattr(es.httpx, "post", fake_post)

    es._send_resend(
        to="guest@example.com",
        subject="Booking confirmation",
        body="hello",
        attachments=[
            es.EmailAttachment(
                filename="Booking #1.pdf", content=b"%PDF-1", subtype="pdf"
            )
        ],
    )

    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["headers"]["Authorization"] == "Bearer re_test_key"
    body = captured["json"]
    assert body["from"] == "info@uzwellness.com"
    assert body["to"] == ["guest@example.com"]
    assert body["subject"] == "Booking confirmation"
    assert body["attachments"][0]["filename"] == "Booking #1.pdf"
    assert body["attachments"][0]["content"] == base64.b64encode(b"%PDF-1").decode()


def test_send_resend_without_key_is_noop(monkeypatch) -> None:
    called = False

    def fake_post(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(es.settings, "RESEND_API_KEY", None)
    monkeypatch.setattr(es.httpx, "post", fake_post)
    es._send_resend(to="x@y.com", subject="s", body="b")
    assert called is False
