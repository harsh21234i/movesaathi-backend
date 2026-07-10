from datetime import datetime, timedelta, timezone

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
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _ride_payload() -> dict[str, object]:
    return {
        "origin": "Pune",
        "destination": "Mumbai",
        "origin_latitude": 18.5204,
        "origin_longitude": 73.8567,
        "destination_latitude": 19.076,
        "destination_longitude": 72.8777,
        "departure_time": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "available_seats": 2,
        "price_per_seat": 500,
        "vehicle_details": "White Innova",
    }


def _create_booking(client) -> tuple[dict[str, str], dict[str, str], int, int]:
    driver_headers = _register_and_login(client, name="Incident Driver", email="incident-driver@example.com", role="driver")
    passenger_headers = _register_and_login(
        client,
        name="Incident Passenger",
        email="incident-passenger@example.com",
        role="passenger",
    )
    ride = client.post("/api/v1/rides", headers=driver_headers, json=_ride_payload())
    assert ride.status_code == 201
    booking = client.post(
        "/api/v1/bookings",
        headers=passenger_headers,
        json={"ride_id": ride.json()["id"], "notes": "Need help with luggage"},
    )
    assert booking.status_code == 200
    return driver_headers, passenger_headers, ride.json()["id"], booking.json()["id"]


def test_passenger_can_report_booking_incident_and_list_it(client) -> None:
    _driver_headers, passenger_headers, _ride_id, booking_id = _create_booking(client)

    response = client.post(
        "/api/v1/incidents",
        headers=passenger_headers,
        json={
            "booking_id": booking_id,
            "title": "Driver asked unsafe pickup",
            "description": "The pickup point changed late and felt unsafe for me.",
            "severity": "high",
        },
    )

    assert response.status_code == 201
    assert response.json()["booking_id"] == booking_id
    assert response.json()["status"] == "open"

    incidents = client.get("/api/v1/incidents", headers=passenger_headers)
    assert incidents.status_code == 200
    assert incidents.json()["items"][0]["title"] == "Driver asked unsafe pickup"


def test_outsider_cannot_report_or_view_unrelated_trip_incident(client) -> None:
    _driver_headers, passenger_headers, _ride_id, booking_id = _create_booking(client)
    outsider_headers = _register_and_login(client, name="Outsider", email="incident-outsider@example.com", role="passenger")

    blocked = client.post(
        "/api/v1/incidents",
        headers=outsider_headers,
        json={
            "booking_id": booking_id,
            "title": "Unrelated report",
            "description": "This passenger should not be able to report this booking.",
        },
    )
    assert blocked.status_code == 404

    created = client.post(
        "/api/v1/incidents",
        headers=passenger_headers,
        json={
            "booking_id": booking_id,
            "title": "Valid report",
            "description": "This is a valid report from the booking passenger.",
        },
    )
    assert created.status_code == 201

    hidden = client.get(f"/api/v1/incidents/{created.json()['id']}", headers=outsider_headers)
    assert hidden.status_code == 404


def test_support_can_filter_and_update_incident_status(client, monkeypatch) -> None:
    monkeypatch.setattr("app.core.config.settings.SUPPORT_API_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.SUPPORT_API_KEY", "support-secret")
    _driver_headers, passenger_headers, ride_id, booking_id = _create_booking(client)

    incident = client.post(
        "/api/v1/incidents",
        headers=passenger_headers,
        json={
            "ride_id": ride_id,
            "booking_id": booking_id,
            "title": "Emergency route issue",
            "description": "The route changed to an unknown road and I need support review.",
            "severity": "emergency",
        },
    )
    assert incident.status_code == 201
    incident_id = incident.json()["id"]
    support_headers = {"x-support-token": "support-secret"}

    listed = client.get(
        "/api/v1/support/incidents",
        headers=support_headers,
        params={"status": "open", "booking_id": booking_id},
    )
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [incident_id]

    updated = client.patch(
        f"/api/v1/support/incidents/{incident_id}",
        headers=support_headers,
        json={"status": "reviewing", "support_notes": "Support agent contacted passenger."},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "reviewing"

    notifications = client.get("/api/v1/notifications", headers=passenger_headers)
    assert notifications.status_code == 200
    assert notifications.json()["items"][0]["type"] == "incident_updated"
