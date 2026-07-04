import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_production_requires_non_default_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="production",
            SECRET_KEY="replace-with-a-strong-32-plus-character-secret",
            BACKEND_CORS_ORIGINS=["https://moovesaathi.example.com"],
            BACKEND_CORS_ORIGIN_REGEX=None,
        )


def test_non_production_can_create_tables() -> None:
    settings = Settings(APP_ENV="test", SECRET_KEY="x" * 32, AUTO_CREATE_TABLES=True)
    assert settings.should_create_tables is True


def test_production_rejects_local_services_and_auto_create_tables() -> None:
    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="production",
            SECRET_KEY="x" * 32,
            BACKEND_CORS_ORIGINS=["https://moovesaathi.example.com"],
            BACKEND_CORS_ORIGIN_REGEX=None,
            DATABASE_URL="sqlite:///./prod.db",
        )

    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="production",
            SECRET_KEY="x" * 32,
            BACKEND_CORS_ORIGINS=["https://moovesaathi.example.com"],
            BACKEND_CORS_ORIGIN_REGEX=None,
            DATABASE_URL="postgresql+psycopg://postgres:postgres@prod-db:5432/moovesaathi",
            REDIS_URL="redis://localhost:6379/0",
        )

    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="production",
            SECRET_KEY="x" * 32,
            BACKEND_CORS_ORIGINS=["https://moovesaathi.example.com"],
            BACKEND_CORS_ORIGIN_REGEX=None,
            DATABASE_URL="postgresql+psycopg://postgres:postgres@prod-db:5432/moovesaathi",
            REDIS_URL="redis://prod-redis:6379/0",
            AUTO_CREATE_TABLES=True,
        )


def test_production_rejects_mock_payment_provider() -> None:
    with pytest.raises(ValidationError, match="PAYMENT_PROVIDER must use a real provider"):
        Settings(
            APP_ENV="production",
            SECRET_KEY="x" * 32,
            BACKEND_CORS_ORIGINS=["https://moovesaathi.example.com"],
            BACKEND_CORS_ORIGIN_REGEX=None,
            DATABASE_URL="postgresql+psycopg://postgres:postgres@prod-db:5432/moovesaathi",
            REDIS_URL="redis://prod-redis:6379/0",
            AUTO_CREATE_TABLES=False,
        )


def test_razorpay_provider_requires_all_credentials() -> None:
    with pytest.raises(ValidationError, match="Razorpay credentials and webhook secret"):
        Settings(
            APP_ENV="test",
            SECRET_KEY="x" * 32,
            PAYMENT_PROVIDER="razorpay",
            RAZORPAY_KEY_ID="rzp_test_public",
        )

    configured = Settings(
        APP_ENV="test",
        SECRET_KEY="x" * 32,
        PAYMENT_PROVIDER="razorpay",
        RAZORPAY_KEY_ID="rzp_test_public",
        RAZORPAY_KEY_SECRET="server-only-secret",
        RAZORPAY_WEBHOOK_SECRET="webhook-secret",
    )
    assert configured.PAYMENT_PROVIDER == "razorpay"
