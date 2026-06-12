from __future__ import annotations

import secrets


class MockPaymentProvider:
    name = "mock"

    def create_payment(self, *, amount: float, currency: str) -> tuple[str, str]:
        provider_payment_id = f"mock_pay_{secrets.token_urlsafe(12)}"
        client_secret = f"mock_secret_{secrets.token_urlsafe(16)}"
        return provider_payment_id, client_secret

    def confirm_payment(self, provider_payment_id: str) -> bool:
        return provider_payment_id.startswith("mock_pay_")

    def capture_payment(self, provider_payment_id: str) -> bool:
        return provider_payment_id.startswith("mock_pay_")

    def refund_payment(self, provider_payment_id: str) -> bool:
        return provider_payment_id.startswith("mock_pay_")


payment_provider = MockPaymentProvider()
