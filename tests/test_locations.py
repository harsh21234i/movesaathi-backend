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


def _create_ride(client, driver_headers: dict[str, str], *, seats: int = 2) -> int:
    response = client.post(
        "/api/v1/rides",
        headers=driver_headers,
        json={
            "origin": "Pune",
            "destination": "Mumbai",
            "origin_latitude": 18.5204,
            "origin_longitude": 73.8567,
            "destination_latitude": 19.076,
            "destination_longitude": 72.8777,
            "departure_time": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "available_seats": seats,
            "price_per_seat": 450,
            "vehicle_details": "White Swift",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_driver_can_update_and_read_latest_location(client) -> None:
    driver_headers = _register_and_login(client, name="Location Driver", email="location-driver@example.com", role="driver")
    ride_id = _create_ride(client, driver_headers)

    update = client.post(
        f"/api/v1/rides/{ride_id}/location",
        headers=driver_headers,
        json={"latitude": 18.53, "longitude": 73.86, "heading": 90, "speed_kmph": 40},
    )
    assert update.status_code == 200
    assert update.json()["latitude"] == 18.53

    latest = client.get(f"/api/v1/rides/{ride_id}/location/latest", headers=driver_headers)
    assert latest.status_code == 200
    assert latest.json()["longitude"] == 73.86


def test_accepted_passenger_can_read_latest_location(client) -> None:
    driver_headers = _register_and_login(client, name="Location Driver 2", email="location-driver-2@example.com", role="driver")
    passenger_headers = _register_and_login(client, name="Location Passenger", email="location-passenger@example.com", role="passenger")
    ride_id = _create_ride(client, driver_headers)
    booking = client.post("/api/v1/bookings", headers=passenger_headers, json={"ride_id": ride_id})
    assert booking.status_code == 200
    accepted = client.patch(f"/api/v1/bookings/{booking.json()['id']}", headers=driver_headers, json={"status": "accepted"})
    assert accepted.status_code == 200
    client.post(f"/api/v1/rides/{ride_id}/location", headers=driver_headers, json={"latitude": 18.54, "longitude": 73.87})

    latest = client.get(f"/api/v1/rides/{ride_id}/location/latest", headers=passenger_headers)

    assert latest.status_code == 200
    assert latest.json()["latitude"] == 18.54


def test_non_participant_cannot_read_location(client) -> None:
    driver_headers = _register_and_login(client, name="Location Driver 3", email="location-driver-3@example.com", role="driver")
    outsider_headers = _register_and_login(client, name="Outsider", email="location-outsider@example.com", role="passenger")
    ride_id = _create_ride(client, driver_headers)
    client.post(f"/api/v1/rides/{ride_id}/location", headers=driver_headers, json={"latitude": 18.55, "longitude": 73.88})

    response = client.get(f"/api/v1/rides/{ride_id}/location/latest", headers=outsider_headers)

    assert response.status_code == 403
    assert response.json()["detail"] == "Location access denied"


def test_driver_cannot_update_location_for_completed_ride(client) -> None:
    driver_headers = _register_and_login(client, name="Location Driver 4", email="location-driver-4@example.com", role="driver")
    ride_id = _create_ride(client, driver_headers)
    completed = client.post(f"/api/v1/rides/{ride_id}/complete", headers=driver_headers)
    assert completed.status_code == 200

    response = client.post(
        f"/api/v1/rides/{ride_id}/location",
        headers=driver_headers,
        json={"latitude": 18.56, "longitude": 73.89},
    )

    assert response.status_code == 400
