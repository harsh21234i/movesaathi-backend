from app.core.config import settings

from tests.helpers import verify_driver_by_email


def _register_and_login(client, *, name: str, email: str, role: str) -> dict[str, str]:
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": name,
            "email": email,
            "password": "Password123",
            "phone_number": "1111111111",
            "role": role,
        },
    )
    assert register_response.status_code == 201
    if role == "driver":
        verify_driver_by_email(email)

    login_response = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123"})
    assert login_response.status_code == 200
    return {"Authorization": f"Bearer {login_response.json()['access_token']}"}


def test_ai_ride_create_assistant_requires_auth(client) -> None:
    response = client.post(
        "/api/v1/ai/ride-create-assistant",
        json={"prompt": "Going from Pune to Nagpur tomorrow 8 AM with 4 seats in Swift for Rs 500"},
    )

    assert response.status_code == 401


def test_ai_ride_create_assistant_is_driver_only(client) -> None:
    passenger_headers = _register_and_login(
        client,
        name="Passenger",
        email="ai-passenger@example.com",
        role="passenger",
    )

    response = client.post(
        "/api/v1/ai/ride-create-assistant",
        headers=passenger_headers,
        json={"prompt": "Going from Pune to Nagpur tomorrow 8 AM with 4 seats in Swift for Rs 500"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Only driver accounts can use the ride creation assistant"


def test_ai_ride_create_assistant_returns_valid_draft_for_driver(client, auth_headers) -> None:
    response = client.post(
        "/api/v1/ai/ride-create-assistant",
        headers=auth_headers,
        json={"prompt": "Going from Pune to Nagpur tomorrow 8 AM with 4 seats in Swift for Rs 500"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "mock"
    assert body["used_fallback"] is False
    assert body["draft"]["origin"] == "Pune"
    assert body["draft"]["destination"] == "Nagpur"
    assert body["draft"]["available_seats"] == 4
    assert body["draft"]["price_per_seat"] == 500.0
    assert body["draft"]["vehicle_details"] == "Swift"
    assert body["draft"]["confidence"] > 0.5


def test_ai_ride_create_assistant_reports_missing_fields(client, auth_headers) -> None:
    response = client.post(
        "/api/v1/ai/ride-create-assistant",
        headers=auth_headers,
        json={"prompt": "I am driving tomorrow morning and can take passengers"},
    )

    assert response.status_code == 200
    body = response.json()
    assert "origin" in body["draft"]["missing_fields"]
    assert "destination" in body["draft"]["missing_fields"]
    assert "price_per_seat" in body["draft"]["missing_fields"]


def test_ai_ride_create_assistant_is_rate_limited(client, auth_headers, rate_limit_settings) -> None:
    payload = {"prompt": "Going from Pune to Nagpur tomorrow 8 AM with 4 seats in Swift for Rs 500"}

    assert client.post("/api/v1/ai/ride-create-assistant", headers=auth_headers, json=payload).status_code == 200
    assert client.post("/api/v1/ai/ride-create-assistant", headers=auth_headers, json=payload).status_code == 200
    assert client.post("/api/v1/ai/ride-create-assistant", headers=auth_headers, json=payload).status_code == 429


def test_ai_service_falls_back_to_mock_when_provider_fails(client, auth_headers, monkeypatch) -> None:
    class FailingProvider:
        provider = "openai"
        model = "broken-model"

        def create_ride_draft(self, *, prompt: str, locale: str, timezone_name: str) -> dict[str, object]:
            raise RuntimeError("provider unavailable")

    from app.services import ai as ai_service_module

    monkeypatch.setattr(settings, "AI_FALLBACK_TO_MOCK", True)
    monkeypatch.setattr(ai_service_module, "get_ai_provider", lambda: FailingProvider())

    response = client.post(
        "/api/v1/ai/ride-create-assistant",
        headers=auth_headers,
        json={"prompt": "Going from Pune to Nagpur tomorrow 8 AM with 4 seats in Swift for Rs 500"},
    )

    assert response.status_code == 200
    assert response.json()["provider"] == "mock"
    assert response.json()["used_fallback"] is True
