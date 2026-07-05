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
    return {"Authorization": f"Bearer {login_response.json()['access_token']}"}


def _create_accepted_booking(client, *, departure_delta: timedelta | None = None) -> tuple[dict[str, str], dict[str, str], int, int]:
    driver_headers = _register_and_login(client, name="Share Driver", email="share-driver@example.com", role="driver")
    passenger_headers = _register_and_login(client, name="Share Passenger", email="share-passenger@example.com", role="passenger")
    departure_time = datetime.now(timezone.utc) + (departure_delta or timedelta(minutes=30))
    ride = client.post(
        "/api/v1/rides",
        headers=driver_headers,
        json={
            "origin": "Pune",
            "destination": "Mumbai",
            "origin_latitude": 18.5204,
            "origin_longitude": 73.8567,
            "destination_latitude": 19.076,
            "destination_longitude": 72.8777,
            "departure_time": departure_time.isoformat(),
            "available_seats": 2,
            "price_per_seat": 500,
            "vehicle_details": "White Innova",
        },
    )
    assert ride.status_code == 201
    booking = client.post(
        "/api/v1/bookings",
        headers=passenger_headers,
        json={"ride_id": ride.json()["id"]},
    )
    assert booking.status_code == 200
    accepted = client.patch(
        f"/api/v1/bookings/{booking.json()['id']}",
        headers=driver_headers,
        json={"status": "accepted"},
    )
    assert accepted.status_code == 200
    return driver_headers, passenger_headers, ride.json()["id"], booking.json()["id"]


def test_passenger_can_share_accepted_trip_and_public_view_is_limited(client) -> None:
    driver_headers, passenger_headers, ride_id, booking_id = _create_accepted_booking(client)
    location = client.post(
        f"/api/v1/rides/{ride_id}/location",
        headers=driver_headers,
        json={"latitude": 18.55, "longitude": 73.88, "heading": 90},
    )
    assert location.status_code == 200

    shared = client.post(f"/api/v1/bookings/{booking_id}/share", headers=passenger_headers)
    assert shared.status_code == 200
    token = shared.json()["token"]

    public = client.get(f"/api/v1/bookings/share/{token}")
    assert public.status_code == 200
    body = public.json()
    assert body["origin"] == "Pune"
    assert body["destination"] == "Mumbai"
    assert body["driver"]["first_name"] == "Share"
    assert "email" not in body["driver"]
    assert body["latest_location"]["latitude"] == 18.55
    assert body["location_visible"] is True


def test_share_token_can_be_revoked(client) -> None:
    _driver_headers, passenger_headers, _ride_id, booking_id = _create_accepted_booking(client)
    shared = client.post(f"/api/v1/bookings/{booking_id}/share", headers=passenger_headers)
    assert shared.status_code == 200

    revoked = client.delete(f"/api/v1/bookings/{booking_id}/share", headers=passenger_headers)
    assert revoked.status_code == 200
    assert revoked.json()["revoked"] is True

    public = client.get(f"/api/v1/bookings/share/{shared.json()['token']}")
    assert public.status_code == 404


def test_unaccepted_or_unowned_booking_cannot_be_shared(client) -> None:
    driver_headers = _register_and_login(client, name="Pending Share Driver", email="pending-share-driver@example.com", role="driver")
    passenger_headers = _register_and_login(client, name="Pending Share Passenger", email="pending-share-passenger@example.com", role="passenger")
    outsider_headers = _register_and_login(client, name="Share Outsider", email="share-outsider@example.com", role="passenger")
    ride = client.post(
        "/api/v1/rides",
        headers=driver_headers,
        json={
            "origin": "Pune",
            "destination": "Mumbai",
            "departure_time": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
            "available_seats": 2,
            "price_per_seat": 500,
            "vehicle_details": "White Innova",
        },
    )
    assert ride.status_code == 201
    booking = client.post("/api/v1/bookings", headers=passenger_headers, json={"ride_id": ride.json()["id"]})
    assert booking.status_code == 200

    pending_share = client.post(f"/api/v1/bookings/{booking.json()['id']}/share", headers=passenger_headers)
    assert pending_share.status_code == 400

    outsider_share = client.post(f"/api/v1/bookings/{booking.json()['id']}/share", headers=outsider_headers)
    assert outsider_share.status_code == 403


def test_public_trip_location_hidden_outside_tracking_window(client) -> None:
    driver_headers, passenger_headers, ride_id, booking_id = _create_accepted_booking(client, departure_delta=timedelta(days=3))
    location = client.post(
        f"/api/v1/rides/{ride_id}/location",
        headers=driver_headers,
        json={"latitude": 18.55, "longitude": 73.88},
    )
    assert location.status_code == 200
    shared = client.post(f"/api/v1/bookings/{booking_id}/share", headers=passenger_headers)
    assert shared.status_code == 200

    public = client.get(f"/api/v1/bookings/share/{shared.json()['token']}")
    assert public.status_code == 200
    assert public.json()["latest_location"] is None
    assert public.json()["location_visible"] is False
