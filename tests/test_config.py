import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_production_requires_non_default_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="production",
            SECRET_KEY="replace-with-a-strong-32-plus-character-secret",
            BACKEND_CORS_ORIGINS=["https://moovesaathi.example.com"],
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
            DATABASE_URL="sqlite:///./prod.db",
        )

    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="production",
            SECRET_KEY="x" * 32,
            BACKEND_CORS_ORIGINS=["https://moovesaathi.example.com"],
            DATABASE_URL="postgresql+psycopg://postgres:postgres@prod-db:5432/moovesaathi",
            REDIS_URL="redis://localhost:6379/0",
        )

    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="production",
            SECRET_KEY="x" * 32,
            BACKEND_CORS_ORIGINS=["https://moovesaathi.example.com"],
            DATABASE_URL="postgresql+psycopg://postgres:postgres@prod-db:5432/moovesaathi",
            REDIS_URL="redis://prod-redis:6379/0",
            AUTO_CREATE_TABLES=True,
        )
