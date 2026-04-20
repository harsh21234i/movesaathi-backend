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


def _create_ride(client, headers: dict[str, str], seats: int = 2) -> int:
    departure_time = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    response = client.post(
        "/api/v1/rides",
        headers=headers,
        json={
            "origin": "Noida",
            "destination": "Delhi",
            "departure_time": departure_time,
            "available_seats": seats,
            "price_per_seat": 150,
            "vehicle_details": "Blue WagonR",
            "notes": "Morning ride",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_driver_cannot_book_own_ride(client) -> None:
    driver_headers = _register_and_login(client, name="Driver", email="driver@example.com", role="driver")
    ride_id = _create_ride(client, driver_headers)

    response = client.post("/api/v1/bookings", headers=driver_headers, json={"ride_id": ride_id, "notes": "me"})

    assert response.status_code == 403
    assert response.json()["detail"] == "Only passenger accounts can book rides"


def test_booking_acceptance_reduces_available_seats(client) -> None:
    driver_headers = _register_and_login(client, name="Driver", email="driver2@example.com", role="driver")
    passenger_headers = _register_and_login(client, name="Passenger", email="passenger@example.com", role="passenger")
    ride_id = _create_ride(client, driver_headers, seats=1)

    create_booking = client.post(
        "/api/v1/bookings",
        headers=passenger_headers,
        json={"ride_id": ride_id, "notes": "Need pickup"},
    )
    assert create_booking.status_code == 200
    booking_id = create_booking.json()["id"]

    accept_booking = client.patch(
        f"/api/v1/bookings/{booking_id}",
        headers=driver_headers,
        json={"status": "accepted"},
    )
    assert accept_booking.status_code == 200
    assert accept_booking.json()["status"] == "accepted"

    rides_response = client.get("/api/v1/rides")
    assert rides_response.status_code == 200
    assert rides_response.json() == []


def test_duplicate_booking_is_rejected(client) -> None:
    driver_headers = _register_and_login(client, name="Driver", email="driver3@example.com", role="driver")
    passenger_headers = _register_and_login(client, name="Passenger", email="passenger2@example.com", role="passenger")
    ride_id = _create_ride(client, driver_headers)

    first_response = client.post("/api/v1/bookings", headers=passenger_headers, json={"ride_id": ride_id})
    second_response = client.post("/api/v1/bookings", headers=passenger_headers, json={"ride_id": ride_id})

    assert first_response.status_code == 200
    assert second_response.status_code == 400
    assert second_response.json()["detail"] == "Passenger already has a booking for this ride"


def test_booking_detail_includes_ride_and_participants(client) -> None:
    driver_headers = _register_and_login(client, name="Driver", email="driver4@example.com", role="driver")
    passenger_headers = _register_and_login(client, name="Passenger", email="passenger4@example.com", role="passenger")
    ride_id = _create_ride(client, driver_headers)

    create_booking = client.post(
        "/api/v1/bookings",
        headers=passenger_headers,
        json={"ride_id": ride_id, "notes": "Need pickup"},
    )
    booking_id = create_booking.json()["id"]

    accept_booking = client.patch(
        f"/api/v1/bookings/{booking_id}",
        headers=driver_headers,
        json={"status": "accepted"},
    )
    assert accept_booking.status_code == 200

    detail_response = client.get(f"/api/v1/bookings/{booking_id}", headers=passenger_headers)

    assert detail_response.status_code == 200
    body = detail_response.json()
    assert body["ride"]["id"] == ride_id
    assert body["driver"]["email"] == "driver4@example.com"
    assert body["passenger"]["email"] == "passenger4@example.com"
    assert body["ride"]["booking_id"] == booking_id
    assert len(body["status_events"]) == 3


def test_passenger_can_cancel_accepted_booking_and_driver_gets_notification(client) -> None:
    driver_headers = _register_and_login(client, name="Driver", email="driver5@example.com", role="driver")
    passenger_headers = _register_and_login(client, name="Passenger", email="passenger5@example.com", role="passenger")
    ride_id = _create_ride(client, driver_headers, seats=1)

    create_booking = client.post("/api/v1/bookings", headers=passenger_headers, json={"ride_id": ride_id})
    booking_id = create_booking.json()["id"]

    accept_booking = client.patch(
        f"/api/v1/bookings/{booking_id}",
        headers=driver_headers,
        json={"status": "accepted"},
    )
    assert accept_booking.status_code == 200

    cancel_booking = client.patch(
        f"/api/v1/bookings/{booking_id}",
        headers=passenger_headers,
        json={"status": "cancelled_by_passenger"},
    )
    assert cancel_booking.status_code == 200
    assert cancel_booking.json()["status"] == "cancelled_by_passenger"

    ride_detail = client.get(f"/api/v1/rides/{ride_id}", headers=driver_headers)
    assert ride_detail.status_code == 200
    assert ride_detail.json()["available_seats"] == 1
    assert ride_detail.json()["status"] == "scheduled"

    notifications = client.get("/api/v1/notifications", headers=driver_headers)
    assert notifications.status_code == 200
    assert notifications.json()[0]["type"] == "booking_cancelled"


def test_driver_can_complete_booking_flow(client) -> None:
    driver_headers = _register_and_login(client, name="Driver", email="driver6@example.com", role="driver")
    passenger_headers = _register_and_login(client, name="Passenger", email="passenger6@example.com", role="passenger")
    ride_id = _create_ride(client, driver_headers, seats=2)

    create_booking = client.post("/api/v1/bookings", headers=passenger_headers, json={"ride_id": ride_id})
    booking_id = create_booking.json()["id"]

    accept_booking = client.patch(
        f"/api/v1/bookings/{booking_id}",
        headers=driver_headers,
        json={"status": "accepted"},
    )
    assert accept_booking.status_code == 200

    complete_booking = client.patch(
        f"/api/v1/bookings/{booking_id}",
        headers=driver_headers,
        json={"status": "completed"},
    )
    assert complete_booking.status_code == 200
    assert complete_booking.json()["status"] == "completed"

    detail_response = client.get(f"/api/v1/bookings/{booking_id}", headers=passenger_headers)
    assert detail_response.status_code == 200
    assert detail_response.json()["status_events"][-1]["label"] == "Trip completed"
