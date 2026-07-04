import hashlib
import hmac
from decimal import Decimal

import httpx

from app.models.payment import PaymentProvider, PaymentStatus
from app.services.payment_provider import RazorpayPaymentProvider, to_minor_units


def _configure_razorpay(monkeypatch) -> None:
    monkeypatch.setattr("app.services.payment_provider.settings.RAZORPAY_KEY_ID", "rzp_test_public")
    monkeypatch.setattr("app.services.payment_provider.settings.RAZORPAY_KEY_SECRET", "server-only-secret")
    monkeypatch.setattr("app.services.payment_provider.settings.RAZORPAY_WEBHOOK_SECRET", "webhook-secret")


def test_to_minor_units_uses_decimal_rounding() -> None:
    assert to_minor_units(Decimal("450.25"), "INR") == 45025
    assert to_minor_units("10.005", "USD") == 1001
    assert to_minor_units("125.5", "JPY") == 126


def test_razorpay_creates_order_without_returning_secret(monkeypatch) -> None:
    _configure_razorpay(monkeypatch)
    observed: dict[str, object] = {}

    def fake_request(method, url, *, auth, json, timeout):
        observed.update(method=method, url=url, auth=auth, json=json, timeout=timeout)
        return httpx.Response(200, json={"id": "order_123"}, request=httpx.Request(method, url))

    monkeypatch.setattr("app.services.payment_provider.httpx.request", fake_request)

    provider = RazorpayPaymentProvider()
    intent = provider.create_payment(amount_minor=45000, currency="inr", receipt="booking-7")

    assert intent.provider == PaymentProvider.razorpay
    assert intent.provider_order_id == "order_123"
    assert intent.provider_payment_id is None
    assert not hasattr(intent, "key_secret")
    assert observed["auth"] == ("rzp_test_public", "server-only-secret")
    assert observed["json"] == {"amount": 45000, "currency": "INR", "receipt": "booking-7"}


def test_razorpay_reconciliation_maps_provider_status(monkeypatch) -> None:
    _configure_razorpay(monkeypatch)

    def fake_request(method, url, *, auth, json, timeout):
        return httpx.Response(
            200,
            json={"items": [{"id": "pay_123", "status": "captured"}]},
            request=httpx.Request(method, url),
        )

    monkeypatch.setattr("app.services.payment_provider.httpx.request", fake_request)

    snapshot = RazorpayPaymentProvider().reconcile_payment("order_123")

    assert snapshot.status == PaymentStatus.captured
    assert snapshot.provider_payment_id == "pay_123"


def test_razorpay_webhook_signature_verification(monkeypatch) -> None:
    _configure_razorpay(monkeypatch)
    body = b'{"event":"payment.captured"}'
    signature = hmac.new(b"webhook-secret", body, hashlib.sha256).hexdigest()
    provider = RazorpayPaymentProvider()

    assert provider.verify_webhook_signature(body, signature) is True
    assert provider.verify_webhook_signature(body, "invalid") is False
