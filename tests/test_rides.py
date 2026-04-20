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


def test_ride_search_supports_limit_and_offset(client, auth_headers) -> None:
    base_departure = datetime.now(timezone.utc) + timedelta(days=1)
    for index, destination in enumerate(["Noida", "Gurugram", "Faridabad"]):
        response = client.post(
            "/api/v1/rides",
            headers=auth_headers,
            json={
                "origin": "Delhi",
                "destination": destination,
                "departure_time": (base_departure + timedelta(hours=index)).isoformat(),
                "available_seats": 3,
                "price_per_seat": 250,
                "vehicle_details": "White Swift",
                "notes": f"Ride {index}",
            },
        )
        assert response.status_code == 201

    first_page = client.get("/api/v1/rides", params={"origin": "Delhi", "limit": 1, "offset": 0})
    second_page = client.get("/api/v1/rides", params={"origin": "Delhi", "limit": 1, "offset": 1})

    assert first_page.status_code == 200
    assert second_page.status_code == 200
    assert len(first_page.json()) == 1
    assert len(second_page.json()) == 1
    assert first_page.json()[0]["id"] != second_page.json()[0]["id"]


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
    assert detail_response.json()["status"] == "cancelled"


def test_driver_can_complete_ride_and_passenger_booking_completes(client) -> None:
    driver_headers = _register_and_login(client, name="Driver", email="ride-complete@example.com", role="driver")
    passenger_headers = _register_and_login(client, name="Passenger", email="ride-complete-passenger@example.com", role="passenger")
    departure_time = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    create_ride = client.post(
        "/api/v1/rides",
        headers=driver_headers,
        json={
            "origin": "Delhi",
            "destination": "Jaipur",
            "departure_time": departure_time,
            "available_seats": 2,
            "price_per_seat": 500,
            "vehicle_details": "Hatchback",
            "notes": "Evening trip",
        },
    )
    ride_id = create_ride.json()["id"]

    create_booking = client.post(
        "/api/v1/bookings",
        headers=passenger_headers,
        json={"ride_id": ride_id, "notes": "Pickup near station"},
    )
    booking_id = create_booking.json()["id"]

    accept_booking = client.patch(
        f"/api/v1/bookings/{booking_id}",
        headers=driver_headers,
        json={"status": "accepted"},
    )
    assert accept_booking.status_code == 200

    complete_ride = client.post(f"/api/v1/rides/{ride_id}/complete", headers=driver_headers)
    assert complete_ride.status_code == 200
    assert complete_ride.json()["status"] == "completed"
    assert complete_ride.json()["is_active"] is False

    booking_detail = client.get(f"/api/v1/bookings/{booking_id}", headers=passenger_headers)
    assert booking_detail.status_code == 200
    assert booking_detail.json()["status"] == "completed"


def test_create_ride_is_idempotent_with_same_key(client, auth_headers) -> None:
    departure_time = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    idempotent_headers = {
        **auth_headers,
        "Idempotency-Key": "ride-create-1",
    }

    first_response = client.post(
        "/api/v1/rides",
        headers=idempotent_headers,
        json={
            "origin": "Pune",
            "destination": "Mumbai",
            "departure_time": departure_time,
            "available_seats": 3,
            "price_per_seat": 400,
            "vehicle_details": "Sedan",
            "notes": "Airport pickup",
        },
    )
    second_response = client.post(
        "/api/v1/rides",
        headers=idempotent_headers,
        json={
            "origin": "Pune",
            "destination": "Mumbai",
            "departure_time": departure_time,
            "available_seats": 3,
            "price_per_seat": 400,
            "vehicle_details": "Sedan",
            "notes": "Airport pickup",
        },
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert first_response.json()["id"] == second_response.json()["id"]
    assert second_response.headers["x-idempotent-replay"] == "true"

    my_rides = client.get("/api/v1/rides/mine", headers=auth_headers)
    assert my_rides.status_code == 200
    assert len(my_rides.json()) == 1


def test_driver_ride_list_supports_status_filter_and_pagination(client) -> None:
    driver_headers = _register_and_login(client, name="Driver", email="ride-list@example.com", role="driver")
    departure_time = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    first_ride = client.post(
        "/api/v1/rides",
        headers=driver_headers,
        json={
            "origin": "Delhi",
            "destination": "Noida",
            "departure_time": departure_time,
            "available_seats": 2,
            "price_per_seat": 200,
            "vehicle_details": "Sedan",
            "notes": "Morning",
        },
    )
    second_ride = client.post(
        "/api/v1/rides",
        headers=driver_headers,
        json={
            "origin": "Delhi",
            "destination": "Jaipur",
            "departure_time": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
            "available_seats": 2,
            "price_per_seat": 500,
            "vehicle_details": "SUV",
            "notes": "Long route",
        },
    )
    assert first_ride.status_code == 201
    assert second_ride.status_code == 201

    cancel_response = client.delete(f"/api/v1/rides/{first_ride.json()['id']}", headers=driver_headers)
    assert cancel_response.status_code == 204

    cancelled_only = client.get("/api/v1/rides/mine", headers=driver_headers, params={"status": "cancelled"})
    paged_all = client.get("/api/v1/rides/mine", headers=driver_headers, params={"limit": 1, "offset": 0})

    assert cancelled_only.status_code == 200
    assert len(cancelled_only.json()) == 1
    assert cancelled_only.json()[0]["status"] == "cancelled"
    assert paged_all.status_code == 200
    assert len(paged_all.json()) == 1
