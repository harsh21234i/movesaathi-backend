from datetime import datetime, timedelta, timezone

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


def test_ai_ride_search_assistant_requires_auth(client) -> None:
    response = client.post(
        "/api/v1/ai/ride-search-assistant",
        json={"prompt": "Find me 2 seats from Pune to Nagpur tomorrow morning under Rs 800"},
    )

    assert response.status_code == 401


def test_ai_ride_search_assistant_is_passenger_only(client, auth_headers) -> None:
    response = client.post(
        "/api/v1/ai/ride-search-assistant",
        headers=auth_headers,
        json={"prompt": "Find me 2 seats from Pune to Nagpur tomorrow morning under Rs 800"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Only passenger accounts can use the ride search assistant"


def test_ai_ride_search_assistant_returns_filters_for_passenger(client) -> None:
    passenger_headers = _register_and_login(
        client,
        name="Passenger",
        email="ai-search-passenger@example.com",
        role="passenger",
    )

    response = client.post(
        "/api/v1/ai/ride-search-assistant",
        headers=passenger_headers,
        json={"prompt": "Find me 2 seats from Pune to Nagpur tomorrow morning under Rs 800"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "mock"
    assert body["used_fallback"] is False
    assert body["filters"]["origin"] == "Pune"
    assert body["filters"]["destination"] == "Nagpur"
    assert body["filters"]["seat_count"] == 2
    assert body["filters"]["max_price_per_seat"] == 800.0
    assert body["filters"]["departure_after"] is not None
    assert body["filters"]["departure_before"] is not None
    assert body["filters"]["confidence"] > 0.5


def test_ai_ride_search_assistant_reports_missing_fields(client) -> None:
    passenger_headers = _register_and_login(
        client,
        name="Passenger",
        email="ai-search-missing@example.com",
        role="passenger",
    )

    response = client.post(
        "/api/v1/ai/ride-search-assistant",
        headers=passenger_headers,
        json={"prompt": "I need a comfortable ride tomorrow morning"},
    )

    assert response.status_code == 200
    body = response.json()
    assert "origin" in body["filters"]["missing_fields"]
    assert "destination" in body["filters"]["missing_fields"]
    assert "seat_count" in body["filters"]["missing_fields"]


def test_ai_ride_search_assistant_is_rate_limited(client, rate_limit_settings) -> None:
    passenger_headers = _register_and_login(
        client,
        name="Passenger",
        email="ai-search-rate@example.com",
        role="passenger",
    )
    payload = {"prompt": "Find me 2 seats from Pune to Nagpur tomorrow morning under Rs 800"}

    assert client.post("/api/v1/ai/ride-search-assistant", headers=passenger_headers, json=payload).status_code == 200
    assert client.post("/api/v1/ai/ride-search-assistant", headers=passenger_headers, json=payload).status_code == 200
    assert client.post("/api/v1/ai/ride-search-assistant", headers=passenger_headers, json=payload).status_code == 429


def test_ai_ride_search_assistant_falls_back_to_mock_when_provider_fails(client, monkeypatch) -> None:
    passenger_headers = _register_and_login(
        client,
        name="Passenger",
        email="ai-search-fallback@example.com",
        role="passenger",
    )

    class FailingProvider:
        provider = "openai"
        model = "broken-model"

        def create_ride_draft(self, *, prompt: str, locale: str, timezone_name: str) -> dict[str, object]:
            raise RuntimeError("provider unavailable")

        def create_ride_search_filters(self, *, prompt: str, locale: str, timezone_name: str) -> dict[str, object]:
            raise RuntimeError("provider unavailable")

    from app.services import ai as ai_service_module

    monkeypatch.setattr(settings, "AI_FALLBACK_TO_MOCK", True)
    monkeypatch.setattr(ai_service_module, "get_ai_provider", lambda: FailingProvider())

    response = client.post(
        "/api/v1/ai/ride-search-assistant",
        headers=passenger_headers,
        json={"prompt": "Find me 2 seats from Pune to Nagpur tomorrow morning under Rs 800"},
    )

    assert response.status_code == 200
    assert response.json()["provider"] == "mock"
    assert response.json()["used_fallback"] is True


def test_ai_service_falls_back_to_mock_when_provider_fails(client, auth_headers, monkeypatch) -> None:
    class FailingProvider:
        provider = "openai"
        model = "broken-model"

        def create_ride_draft(self, *, prompt: str, locale: str, timezone_name: str) -> dict[str, object]:
            raise RuntimeError("provider unavailable")

        def create_ride_search_filters(self, *, prompt: str, locale: str, timezone_name: str) -> dict[str, object]:
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


def _create_booking(client):
    driver_headers = _register_and_login(client, name="AI Chat Driver", email="ai-chat-driver@example.com", role="driver")
    passenger_headers = _register_and_login(client, name="AI Chat Passenger", email="ai-chat-passenger@example.com", role="passenger")

    departure_time = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    ride_response = client.post(
        "/api/v1/rides",
        headers=driver_headers,
        json={
            "origin": "Pune",
            "destination": "Mumbai",
            "departure_time": departure_time,
            "available_seats": 2,
            "price_per_seat": 300,
            "vehicle_details": "Silver Baleno",
            "notes": "Evening ride",
        },
    )
    assert ride_response.status_code == 201

    booking_response = client.post(
        "/api/v1/bookings",
        headers=passenger_headers,
        json={"ride_id": ride_response.json()["id"], "notes": "Window seat if possible"},
    )
    assert booking_response.status_code == 200
    return booking_response.json()["id"], passenger_headers, driver_headers


def test_ai_chat_suggestion_requires_auth(client) -> None:
    response = client.post(
        "/api/v1/ai/chat-suggestion",
        json={"booking_id": 1, "intent": "ask_pickup_confirmation"},
    )

    assert response.status_code == 401


def test_ai_chat_suggestion_requires_booking_participant(client) -> None:
    booking_id, _, _ = _create_booking(client)
    outsider_headers = _register_and_login(client, name="Outsider", email="ai-chat-outsider@example.com", role="passenger")

    response = client.post(
        "/api/v1/ai/chat-suggestion",
        headers=outsider_headers,
        json={"booking_id": booking_id, "intent": "ask_pickup_confirmation"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Chat access denied"


def test_ai_chat_suggestion_returns_passenger_pickup_reply(client) -> None:
    booking_id, passenger_headers, _ = _create_booking(client)

    response = client.post(
        "/api/v1/ai/chat-suggestion",
        headers=passenger_headers,
        json={
            "booking_id": booking_id,
            "intent": "ask_pickup_confirmation",
            "draft_message": "where are you coming",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "mock"
    assert body["used_fallback"] is False
    assert "Pune to Mumbai" in body["booking_summary"]
    assert "pickup point" in body["result"]["suggestion"].lower()
    assert body["result"]["tone"] == "polite"


def test_ai_chat_suggestion_returns_driver_arrival_reply(client) -> None:
    booking_id, _, driver_headers = _create_booking(client)

    response = client.post(
        "/api/v1/ai/chat-suggestion",
        headers=driver_headers,
        json={"booking_id": booking_id, "intent": "share_arrival_update"},
    )

    assert response.status_code == 200
    body = response.json()
    assert "Pune to Mumbai" in body["result"]["suggestion"]
    assert "Silver Baleno" in body["result"]["suggestion"]


def test_ai_chat_suggestion_warns_for_sensitive_draft(client) -> None:
    booking_id, passenger_headers, _ = _create_booking(client)

    response = client.post(
        "/api/v1/ai/chat-suggestion",
        headers=passenger_headers,
        json={
            "booking_id": booking_id,
            "intent": "general_reply",
            "draft_message": "my otp is 123456 and card cvv is 123",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["result"]["should_warn"] is True
    assert body["result"]["tone"] == "safety_warning"
    assert any("sensitive" in note.lower() for note in body["result"]["safety_notes"])


def test_ai_chat_suggestion_is_rate_limited(client, rate_limit_settings) -> None:
    booking_id, passenger_headers, _ = _create_booking(client)
    payload = {"booking_id": booking_id, "intent": "general_reply"}

    assert client.post("/api/v1/ai/chat-suggestion", headers=passenger_headers, json=payload).status_code == 200
    assert client.post("/api/v1/ai/chat-suggestion", headers=passenger_headers, json=payload).status_code == 200
    assert client.post("/api/v1/ai/chat-suggestion", headers=passenger_headers, json=payload).status_code == 429


def test_ai_chat_suggestion_falls_back_to_mock_when_provider_fails(client, monkeypatch) -> None:
    booking_id, local_passenger_headers, _ = _create_booking(client)

    class FailingProvider:
        provider = "openai"
        model = "broken-model"

        def create_ride_draft(self, *, prompt: str, locale: str, timezone_name: str) -> dict[str, object]:
            raise RuntimeError("provider unavailable")

        def suggest_chat_reply(
            self,
            *,
            intent: str,
            draft_message: str | None,
            sender_role: str,
            booking_context: dict[str, object],
            locale: str,
        ) -> dict[str, object]:
            raise RuntimeError("provider unavailable")

    from app.services import ai as ai_service_module

    monkeypatch.setattr(settings, "AI_FALLBACK_TO_MOCK", True)
    monkeypatch.setattr(ai_service_module, "get_ai_provider", lambda: FailingProvider())

    response = client.post(
        "/api/v1/ai/chat-suggestion",
        headers=local_passenger_headers,
        json={"booking_id": booking_id, "intent": "general_reply"},
    )

    assert response.status_code == 200
    assert response.json()["provider"] == "mock"
    assert response.json()["used_fallback"] is True
