from datetime import datetime, timedelta, timezone


def test_create_and_search_ride(client, auth_headers) -> None:
    departure_time = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    create_response = client.post(
        "/api/v1/rides",
        headers=auth_headers,
        json={
            "origin": "Delhi",
            "destination": "Gurugram",
            "departure_time": departure_time,
            "available_seats": 3,
            "price_per_seat": 250,
            "vehicle_details": "White Swift",
            "notes": "No smoking",
        },
    )

    assert create_response.status_code == 201
    assert create_response.json()["origin"] == "Delhi"

    search_response = client.get("/api/v1/rides", params={"origin": "Del", "destination": "Guru"})
    assert search_response.status_code == 200
    assert len(search_response.json()) == 1
    assert search_response.json()[0]["destination"] == "Gurugram"


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


def test_get_ride_detail_includes_driver_and_booking_context(client) -> None:
    driver_headers = _register_and_login(client, name="Driver", email="ride-driver@example.com", role="driver")
    passenger_headers = _register_and_login(client, name="Passenger", email="ride-passenger@example.com", role="passenger")
    departure_time = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    create_ride = client.post(
        "/api/v1/rides",
        headers=driver_headers,
        json={
            "origin": "Delhi",
            "destination": "Noida",
            "departure_time": departure_time,
            "available_seats": 2,
            "price_per_seat": 220,
            "vehicle_details": "Sedan",
            "notes": "Near metro gate",
        },
    )
    ride_id = create_ride.json()["id"]

    create_booking = client.post(
        "/api/v1/bookings",
        headers=passenger_headers,
        json={"ride_id": ride_id, "notes": "Window seat"},
    )
    booking_id = create_booking.json()["id"]

    detail_response = client.get(f"/api/v1/rides/{ride_id}", headers=passenger_headers)

    assert detail_response.status_code == 200
    body = detail_response.json()
    assert body["driver"]["email"] == "ride-driver@example.com"
    assert body["booking_id"] == booking_id
    assert body["booked_passengers"] == 0
    assert body["passengers"] == []


def test_driver_can_update_and_cancel_ride(client) -> None:
    driver_headers = _register_and_login(client, name="Driver", email="ride-edit@example.com", role="driver")
    departure_time = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    create_ride = client.post(
        "/api/v1/rides",
        headers=driver_headers,
        json={
            "origin": "Delhi",
            "destination": "Noida",
            "departure_time": departure_time,
            "available_seats": 3,
            "price_per_seat": 220,
            "vehicle_details": "Sedan",
            "notes": "Near metro gate",
        },
    )
    ride_id = create_ride.json()["id"]

    update_response = client.patch(
        f"/api/v1/rides/{ride_id}",
        headers=driver_headers,
        json={
            "origin": "Delhi",
            "destination": "Gurugram",
            "departure_time": departure_time,
            "available_seats": 2,
            "price_per_seat": 300,
            "vehicle_details": "SUV",
            "notes": "Updated pickup point",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["destination"] == "Gurugram"
    assert update_response.json()["available_seats"] == 2

    cancel_response = client.delete(f"/api/v1/rides/{ride_id}", headers=driver_headers)
    assert cancel_response.status_code == 204

    detail_response = client.get(f"/api/v1/rides/{ride_id}", headers=driver_headers)
    assert detail_response.status_code == 200
    assert detail_response.json()["is_active"] is False
