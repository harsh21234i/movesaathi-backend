from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from redis.exceptions import RedisError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_db
from app.core.config import settings
from app.db.base import Base
from app.main import app
from app.core.rate_limit import rate_limiter
from app.services.token_store import token_store


SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    future=True,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)


class UnavailableRedis:
    def incr(self, *args, **kwargs):
        raise RedisError("redis unavailable in tests")

    def expire(self, *args, **kwargs):
        raise RedisError("redis unavailable in tests")

    def setex(self, *args, **kwargs):
        raise RedisError("redis unavailable in tests")

    def exists(self, *args, **kwargs):
        raise RedisError("redis unavailable in tests")


@pytest.fixture(autouse=True)
def setup_database(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(rate_limiter, "_redis", UnavailableRedis())
    monkeypatch.setattr(token_store, "_client", UnavailableRedis())
    token_store._in_memory_tokens.clear()
    rate_limiter.reset()
    yield
    Base.metadata.drop_all(bind=engine)
    token_store._in_memory_tokens.clear()
    rate_limiter.reset()


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setattr("app.main.initialize_database", lambda: None)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Alice Rider",
            "email": "alice@example.com",
            "password": "Password123",
            "phone_number": "1234567890",
            "role": "driver",
        },
    )
    assert response.status_code == 201

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "Password123"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def rate_limit_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LOGIN_RATE_LIMIT_MAX_REQUESTS", 2)
    monkeypatch.setattr(settings, "FORGOT_PASSWORD_RATE_LIMIT_MAX_REQUESTS", 2)
    monkeypatch.setattr(settings, "RESET_PASSWORD_RATE_LIMIT_MAX_REQUESTS", 2)
    monkeypatch.setattr(settings, "RESEND_VERIFICATION_RATE_LIMIT_MAX_REQUESTS", 2)
    monkeypatch.setattr(settings, "CHAT_MESSAGE_RATE_LIMIT_MAX_REQUESTS", 2)
