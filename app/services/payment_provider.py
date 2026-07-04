from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Protocol

import httpx

from app.core.config import settings
from app.models.payment import PaymentProvider, PaymentStatus


@dataclass(frozen=True, slots=True)
class ProviderPaymentIntent:
    provider: PaymentProvider
    provider_order_id: str
    provider_payment_id: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderPaymentSnapshot:
    status: PaymentStatus
    provider_payment_id: str | None = None


class PaymentGateway(Protocol):
    provider: PaymentProvider
    checkout_key_id: str | None

    def create_payment(self, *, amount_minor: int, currency: str, receipt: str) -> ProviderPaymentIntent: ...

    def confirm_payment(self, provider_order_id: str) -> ProviderPaymentSnapshot: ...

    def capture_payment(self, provider_payment_id: str, *, amount_minor: int, currency: str) -> bool: ...

    def refund_payment(self, provider_payment_id: str, *, amount_minor: int) -> bool: ...

    def reconcile_payment(self, provider_order_id: str) -> ProviderPaymentSnapshot: ...

    def verify_webhook_signature(self, body: bytes, signature: str) -> bool: ...


def to_minor_units(amount: Decimal | float | int | str, currency: str) -> int:
    value = Decimal(str(amount))
    exponent = 0 if currency.upper() in {"JPY"} else 2
    factor = Decimal(10) ** exponent
    return int((value * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class MockPaymentProvider:
    provider = PaymentProvider.mock
    checkout_key_id = None

    def create_payment(self, *, amount_minor: int, currency: str, receipt: str) -> ProviderPaymentIntent:
        order_id = f"mock_order_{secrets.token_urlsafe(12)}"
        return ProviderPaymentIntent(
            provider=self.provider,
            provider_order_id=order_id,
            provider_payment_id=f"mock_pay_{secrets.token_urlsafe(12)}",
        )

    def confirm_payment(self, provider_order_id: str) -> ProviderPaymentSnapshot:
        return ProviderPaymentSnapshot(status=PaymentStatus.authorized)

    def capture_payment(self, provider_payment_id: str, *, amount_minor: int, currency: str) -> bool:
        return provider_payment_id.startswith("mock_pay_")

    def refund_payment(self, provider_payment_id: str, *, amount_minor: int) -> bool:
        return provider_payment_id.startswith("mock_pay_")

    def reconcile_payment(self, provider_order_id: str) -> ProviderPaymentSnapshot:
        return ProviderPaymentSnapshot(status=PaymentStatus.authorized)

    def verify_webhook_signature(self, body: bytes, signature: str) -> bool:
        return settings.APP_ENV != "production"


class RazorpayPaymentProvider:
    provider = PaymentProvider.razorpay
    base_url = "https://api.razorpay.com/v1"

    def __init__(self) -> None:
        if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET or not settings.RAZORPAY_WEBHOOK_SECRET:
            raise RuntimeError("Razorpay credentials are not configured")
        self.key_id = settings.RAZORPAY_KEY_ID
        self.key_secret = settings.RAZORPAY_KEY_SECRET
        self.webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET
        self.checkout_key_id = self.key_id

    def create_payment(self, *, amount_minor: int, currency: str, receipt: str) -> ProviderPaymentIntent:
        data = self._request(
            "POST",
            "/orders",
            json={"amount": amount_minor, "currency": currency.upper(), "receipt": receipt[:40]},
        )
        return ProviderPaymentIntent(provider=self.provider, provider_order_id=str(data["id"]))

    def confirm_payment(self, provider_order_id: str) -> ProviderPaymentSnapshot:
        return self.reconcile_payment(provider_order_id)

    def capture_payment(self, provider_payment_id: str, *, amount_minor: int, currency: str) -> bool:
        data = self._request(
            "POST",
            f"/payments/{provider_payment_id}/capture",
            json={"amount": amount_minor, "currency": currency.upper()},
        )
        return data.get("status") == "captured"

    def refund_payment(self, provider_payment_id: str, *, amount_minor: int) -> bool:
        data = self._request("POST", f"/payments/{provider_payment_id}/refund", json={"amount": amount_minor})
        return data.get("status") in {"pending", "processed"}

    def reconcile_payment(self, provider_order_id: str) -> ProviderPaymentSnapshot:
        data = self._request("GET", f"/orders/{provider_order_id}/payments")
        items = data.get("items", [])
        if not items:
            return ProviderPaymentSnapshot(status=PaymentStatus.pending)
        payment = items[-1]
        provider_payment_id = str(payment["id"])
        status_map = {
            "authorized": PaymentStatus.authorized,
            "captured": PaymentStatus.captured,
            "failed": PaymentStatus.failed,
            "refunded": PaymentStatus.refunded,
        }
        return ProviderPaymentSnapshot(
            status=status_map.get(str(payment.get("status")), PaymentStatus.pending),
            provider_payment_id=provider_payment_id,
        )

    def verify_webhook_signature(self, body: bytes, signature: str) -> bool:
        expected = hmac.new(self.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def _request(self, method: str, path: str, *, json: dict[str, object] | None = None) -> dict[str, object]:
        response = httpx.request(
            method,
            f"{self.base_url}{path}",
            auth=(self.key_id, self.key_secret),
            json=json,
            timeout=settings.PAYMENT_PROVIDER_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()


def get_payment_provider(provider: PaymentProvider | str | None = None) -> PaymentGateway:
    selected_provider = provider.value if isinstance(provider, PaymentProvider) else provider
    if selected_provider is None:
        selected_provider = settings.PAYMENT_PROVIDER
    if selected_provider == PaymentProvider.razorpay.value:
        return RazorpayPaymentProvider()
    return MockPaymentProvider()
