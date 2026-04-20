from datetime import datetime, timedelta, timezone


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
    login_response = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123"})
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_booking(client):
    driver_headers = _register_and_login(client, name="Driver Chat", email="driver-chat@example.com", role="driver")
    passenger_headers = _register_and_login(client, name="Passenger Chat", email="passenger-chat@example.com", role="passenger")

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
    ride_id = ride_response.json()["id"]

    booking_response = client.post(
        "/api/v1/bookings",
        headers=passenger_headers,
        json={"ride_id": ride_id, "notes": "Window seat if possible"},
    )
    assert booking_response.status_code == 200
    return booking_response.json()["id"], passenger_headers, driver_headers


def test_chat_message_rate_limit(client, rate_limit_settings) -> None:
    booking_id, passenger_headers, _ = _create_booking(client)

    assert client.post(
        "/api/v1/chat/messages",
        headers=passenger_headers,
        json={"booking_id": booking_id, "content": "hello"},
    ).status_code == 200
    assert client.post(
        "/api/v1/chat/messages",
        headers=passenger_headers,
        json={"booking_id": booking_id, "content": "are you there?"},
    ).status_code == 200

    blocked = client.post(
        "/api/v1/chat/messages",
        headers=passenger_headers,
        json={"booking_id": booking_id, "content": "third message"},
    )
    assert blocked.status_code == 429


def test_mark_messages_seen_updates_existing_messages(client) -> None:
    booking_id, passenger_headers, driver_headers = _create_booking(client)

    sent = client.post(
        "/api/v1/chat/messages",
        headers=driver_headers,
        json={"booking_id": booking_id, "content": "Pickup near gate 2"},
    )
    assert sent.status_code == 200
    message_id = sent.json()["id"]
    assert sent.json()["seen_at"] is None

    seen_response = client.post(f"/api/v1/chat/{booking_id}/seen", headers=passenger_headers)
    assert seen_response.status_code == 200
    body = seen_response.json()
    assert body["updated"] == 1
    assert body["message_ids"] == [message_id]
    assert body["seen_at"] is not None

    messages_response = client.get(f"/api/v1/chat/{booking_id}/messages", headers=driver_headers)
    assert messages_response.status_code == 200
    assert messages_response.json()[0]["seen_at"] is not None


def test_mark_messages_seen_does_not_mark_own_messages(client) -> None:
    booking_id, passenger_headers, _ = _create_booking(client)

    sent = client.post(
        "/api/v1/chat/messages",
        headers=passenger_headers,
        json={"booking_id": booking_id, "content": "I will bring one bag"},
    )
    assert sent.status_code == 200

    seen_response = client.post(f"/api/v1/chat/{booking_id}/seen", headers=passenger_headers)
    assert seen_response.status_code == 200
    assert seen_response.json()["updated"] == 0
