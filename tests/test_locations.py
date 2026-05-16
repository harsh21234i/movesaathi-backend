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


def _create_ride(client, driver_headers: dict[str, str], *, seats: int = 2, departure_delta: timedelta | None = None) -> int:
    departure_delta = departure_delta or timedelta(minutes=30)
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
            "departure_time": (datetime.now(timezone.utc) + departure_delta).isoformat(),
            "available_seats": seats,
            "price_per_seat": 450,
            "vehicle_details": "White Swift",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _create_ride_without_coordinates(client, driver_headers: dict[str, str]) -> int:
    response = client.post(
        "/api/v1/rides",
        headers=driver_headers,
        json={
            "origin": "Pune",
            "destination": "Mumbai",
            "departure_time": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
            "available_seats": 2,
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
    assert latest.json()["age_seconds"] >= 0
    assert latest.json()["is_stale"] is False


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
    assert latest.json()["is_stale"] is False


def test_driver_can_read_location_history_newest_first(client) -> None:
    driver_headers = _register_and_login(client, name="Location Driver History", email="location-history-driver@example.com", role="driver")
    ride_id = _create_ride(client, driver_headers)
    for latitude in [18.51, 18.52, 18.53]:
        response = client.post(
            f"/api/v1/rides/{ride_id}/location",
            headers=driver_headers,
            json={"latitude": latitude, "longitude": 73.86},
        )
        assert response.status_code == 200

    history = client.get(f"/api/v1/rides/{ride_id}/location/history", headers=driver_headers, params={"limit": 2})

    assert history.status_code == 200
    body = history.json()
    assert len(body) == 2
    assert [item["latitude"] for item in body] == [18.53, 18.52]
    assert all("age_seconds" in item and "is_stale" in item for item in body)


def test_accepted_passenger_can_read_location_history(client) -> None:
    driver_headers = _register_and_login(client, name="Location Driver 5", email="location-driver-5@example.com", role="driver")
    passenger_headers = _register_and_login(client, name="Location Passenger 2", email="location-passenger-2@example.com", role="passenger")
    ride_id = _create_ride(client, driver_headers)
    booking = client.post("/api/v1/bookings", headers=passenger_headers, json={"ride_id": ride_id})
    assert booking.status_code == 200
    accepted = client.patch(f"/api/v1/bookings/{booking.json()['id']}", headers=driver_headers, json={"status": "accepted"})
    assert accepted.status_code == 200
    client.post(f"/api/v1/rides/{ride_id}/location", headers=driver_headers, json={"latitude": 18.54, "longitude": 73.87})

    history = client.get(f"/api/v1/rides/{ride_id}/location/history", headers=passenger_headers)

    assert history.status_code == 200
    assert history.json()[0]["longitude"] == 73.87


def test_accepted_passenger_cannot_track_far_before_ride_time(client) -> None:
    driver_headers = _register_and_login(client, name="Future Driver", email="future-location-driver@example.com", role="driver")
    passenger_headers = _register_and_login(client, name="Future Passenger", email="future-location-passenger@example.com", role="passenger")
    ride_id = _create_ride(client, driver_headers, departure_delta=timedelta(days=2))
    booking = client.post("/api/v1/bookings", headers=passenger_headers, json={"ride_id": ride_id})
    assert booking.status_code == 200
    accepted = client.patch(f"/api/v1/bookings/{booking.json()['id']}", headers=driver_headers, json={"status": "accepted"})
    assert accepted.status_code == 200
    client.post(f"/api/v1/rides/{ride_id}/location", headers=driver_headers, json={"latitude": 18.54, "longitude": 73.87})

    latest = client.get(f"/api/v1/rides/{ride_id}/location/latest", headers=passenger_headers)

    assert latest.status_code == 403
    assert latest.json()["detail"] == "Location tracking is only available near ride time"


def test_location_access_endpoint_reports_driver_access(client) -> None:
    driver_headers = _register_and_login(client, name="Access Driver", email="access-driver@example.com", role="driver")
    ride_id = _create_ride(client, driver_headers)

    response = client.get(f"/api/v1/rides/{ride_id}/location/access", headers=driver_headers)

    assert response.status_code == 200
    assert response.json()["can_track"] is True
    assert response.json()["reason"] is None


def test_location_access_endpoint_reports_time_window_denial(client) -> None:
    driver_headers = _register_and_login(client, name="Access Future Driver", email="access-future-driver@example.com", role="driver")
    passenger_headers = _register_and_login(client, name="Access Future Passenger", email="access-future-passenger@example.com", role="passenger")
    ride_id = _create_ride(client, driver_headers, departure_delta=timedelta(days=2))
    booking = client.post("/api/v1/bookings", headers=passenger_headers, json={"ride_id": ride_id})
    assert booking.status_code == 200
    accepted = client.patch(f"/api/v1/bookings/{booking.json()['id']}", headers=driver_headers, json={"status": "accepted"})
    assert accepted.status_code == 200

    response = client.get(f"/api/v1/rides/{ride_id}/location/access", headers=passenger_headers)

    assert response.status_code == 200
    assert response.json()["can_track"] is False
    assert response.json()["reason"] == "Location tracking is only available near ride time"
    assert response.json()["tracking_starts_at"] is not None
    assert response.json()["tracking_ends_at"] is not None


def test_location_access_endpoint_reports_outsider_denial(client) -> None:
    driver_headers = _register_and_login(client, name="Access Outsider Driver", email="access-outsider-driver@example.com", role="driver")
    outsider_headers = _register_and_login(client, name="Access Outsider", email="access-outsider@example.com", role="passenger")
    ride_id = _create_ride(client, driver_headers)

    response = client.get(f"/api/v1/rides/{ride_id}/location/access", headers=outsider_headers)

    assert response.status_code == 200
    assert response.json()["can_track"] is False
    assert response.json()["reason"] == "Location access denied"


def test_non_participant_cannot_read_location(client) -> None:
    driver_headers = _register_and_login(client, name="Location Driver 3", email="location-driver-3@example.com", role="driver")
    outsider_headers = _register_and_login(client, name="Outsider", email="location-outsider@example.com", role="passenger")
    ride_id = _create_ride(client, driver_headers)
    client.post(f"/api/v1/rides/{ride_id}/location", headers=driver_headers, json={"latitude": 18.55, "longitude": 73.88})

    response = client.get(f"/api/v1/rides/{ride_id}/location/latest", headers=outsider_headers)

    assert response.status_code == 403
    assert response.json()["detail"] == "Location access denied"


def test_non_participant_cannot_read_location_history(client) -> None:
    driver_headers = _register_and_login(client, name="Location Driver 6", email="location-driver-6@example.com", role="driver")
    outsider_headers = _register_and_login(client, name="Outsider History", email="location-outsider-history@example.com", role="passenger")
    ride_id = _create_ride(client, driver_headers)
    client.post(f"/api/v1/rides/{ride_id}/location", headers=driver_headers, json={"latitude": 18.55, "longitude": 73.88})

    response = client.get(f"/api/v1/rides/{ride_id}/location/history", headers=outsider_headers)

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


def test_driver_cannot_report_excessive_location_speed(client) -> None:
    driver_headers = _register_and_login(client, name="Speed Driver", email="speed-location-driver@example.com", role="driver")
    ride_id = _create_ride(client, driver_headers)

    response = client.post(
        f"/api/v1/rides/{ride_id}/location",
        headers=driver_headers,
        json={"latitude": 18.56, "longitude": 73.89, "speed_kmph": 240},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Reported speed is too high for ride tracking"


def test_driver_cannot_update_location_far_from_route(client) -> None:
    driver_headers = _register_and_login(client, name="Route Guard Driver", email="route-guard-driver@example.com", role="driver")
    ride_id = _create_ride(client, driver_headers)

    response = client.post(
        f"/api/v1/rides/{ride_id}/location",
        headers=driver_headers,
        json={"latitude": 28.6139, "longitude": 77.209},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Location is too far from this ride route"


def test_driver_can_update_location_near_route(client) -> None:
    driver_headers = _register_and_login(client, name="Route Near Driver", email="route-near-driver@example.com", role="driver")
    ride_id = _create_ride(client, driver_headers)

    response = client.post(
        f"/api/v1/rides/{ride_id}/location",
        headers=driver_headers,
        json={"latitude": 18.676, "longitude": 73.55},
    )

    assert response.status_code == 200
    assert response.json()["latitude"] == 18.676


def test_location_route_guard_is_skipped_when_route_coordinates_missing(client) -> None:
    driver_headers = _register_and_login(client, name="No Coordinate Driver", email="no-coordinate-driver@example.com", role="driver")
    ride_id = _create_ride_without_coordinates(client, driver_headers)

    response = client.post(
        f"/api/v1/rides/{ride_id}/location",
        headers=driver_headers,
        json={"latitude": 28.6139, "longitude": 77.209},
    )

    assert response.status_code == 200
    assert response.json()["latitude"] == 28.6139
