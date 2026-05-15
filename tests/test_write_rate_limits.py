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
    return {"Authorization": f"Bearer {login_response.json()['access_token']}"}


def _ride_payload(index: int = 0) -> dict[str, object]:
    return {
        "origin": f"Pune {index}",
        "destination": f"Mumbai {index}",
        "departure_time": (datetime.now(timezone.utc) + timedelta(days=1, hours=index)).isoformat(),
        "available_seats": 3,
        "price_per_seat": 450,
        "vehicle_details": "White Swift",
    }


def test_ride_write_rate_limit_applies_to_create_ride(client, rate_limit_settings) -> None:
    driver_headers = _register_and_login(client, name="Limited Driver", email="limited-driver@example.com", role="driver")

    assert client.post("/api/v1/rides", headers=driver_headers, json=_ride_payload(1)).status_code == 201
    assert client.post("/api/v1/rides", headers=driver_headers, json=_ride_payload(2)).status_code == 201
    limited = client.post("/api/v1/rides", headers=driver_headers, json=_ride_payload(3))

    assert limited.status_code == 429
    assert limited.json()["detail"] == "Rate limit exceeded"


def test_location_update_rate_limit_applies(client, rate_limit_settings) -> None:
    driver_headers = _register_and_login(client, name="Limited Location Driver", email="limited-location-driver@example.com", role="driver")
    ride = client.post("/api/v1/rides", headers=driver_headers, json=_ride_payload(1))
    assert ride.status_code == 201
    ride_id = ride.json()["id"]

    assert client.post(f"/api/v1/rides/{ride_id}/location", headers=driver_headers, json={"latitude": 18.51, "longitude": 73.86}).status_code == 200
    assert client.post(f"/api/v1/rides/{ride_id}/location", headers=driver_headers, json={"latitude": 18.52, "longitude": 73.86}).status_code == 200
    limited = client.post(f"/api/v1/rides/{ride_id}/location", headers=driver_headers, json={"latitude": 18.53, "longitude": 73.86})

    assert limited.status_code == 429


def test_booking_write_rate_limit_applies_to_booking_requests(client, rate_limit_settings, monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "RIDE_WRITE_RATE_LIMIT_MAX_REQUESTS", 10)
    driver_headers = _register_and_login(client, name="Booking Limit Driver", email="booking-limit-driver@example.com", role="driver")
    passenger_headers = _register_and_login(client, name="Booking Limit Passenger", email="booking-limit-passenger@example.com", role="passenger")
    ride_ids: list[int] = []
    for index in range(3):
        ride = client.post("/api/v1/rides", headers=driver_headers, json=_ride_payload(index))
        assert ride.status_code == 201
        ride_ids.append(ride.json()["id"])

    assert client.post("/api/v1/bookings", headers=passenger_headers, json={"ride_id": ride_ids[0]}).status_code == 200
    assert client.post("/api/v1/bookings", headers=passenger_headers, json={"ride_id": ride_ids[1]}).status_code == 200
    limited = client.post("/api/v1/bookings", headers=passenger_headers, json={"ride_id": ride_ids[2]})

    assert limited.status_code == 429
