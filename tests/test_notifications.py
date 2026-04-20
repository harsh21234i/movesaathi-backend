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


def test_notification_listing_and_read_state(client) -> None:
    driver_headers = _register_and_login(client, name="Driver", email="notify-driver@example.com", role="driver")
    passenger_headers = _register_and_login(client, name="Passenger", email="notify-passenger@example.com", role="passenger")
    departure_time = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    create_ride = client.post(
        "/api/v1/rides",
        headers=driver_headers,
        json={
            "origin": "Noida",
            "destination": "Delhi",
            "departure_time": departure_time,
            "available_seats": 2,
            "price_per_seat": 100,
            "vehicle_details": "Blue WagonR",
            "notes": "Morning ride",
        },
    )
    ride_id = create_ride.json()["id"]

    create_booking = client.post(
        "/api/v1/bookings",
        headers=passenger_headers,
        json={"ride_id": ride_id, "notes": "Near gate"},
    )
    assert create_booking.status_code == 200

    notifications = client.get("/api/v1/notifications", headers=driver_headers)
    assert notifications.status_code == 200
    body = notifications.json()
    assert len(body) == 1
    assert body[0]["type"] == "booking_requested"
    assert body[0]["is_read"] is False

    mark_read = client.patch(f"/api/v1/notifications/{body[0]['id']}/read", headers=driver_headers)
    assert mark_read.status_code == 200
    assert mark_read.json()["is_read"] is True

    mark_all = client.patch("/api/v1/notifications/read-all", headers=driver_headers)
    assert mark_all.status_code == 200
    assert mark_all.json()["updated"] == 0
