def _register_and_login_driver(client, email: str = "driver-profile@example.com") -> str:
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Driver Profile User",
            "email": email,
            "password": "Password123",
            "phone_number": "9191919191",
            "role": "driver",
        },
    )
    assert register_response.status_code == 201

    login_response = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123"})
    assert login_response.status_code == 200
    return login_response.json()["access_token"]


def test_driver_profile_defaults_to_pending(client) -> None:
    token = _register_and_login_driver(client)

    response = client.get("/api/v1/users/me/driver-profile", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["driver_verification_status"] == "pending"
    assert body["vehicle_make"] is None
    assert body["driver_license_number"] is None


def test_driver_can_update_verification_profile(client) -> None:
    token = _register_and_login_driver(client, email="driver-update@example.com")

    update_response = client.patch(
        "/api/v1/users/me/driver-profile",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "vehicle_make": "Toyota",
            "vehicle_model": "Innova",
            "vehicle_color": "White",
            "vehicle_plate_number": "MH12AB1234",
            "driver_license_number": "DL-1234567890",
        },
    )
    assert update_response.status_code == 200
    body = update_response.json()
    assert body["driver_verification_status"] == "pending"
    assert body["vehicle_make"] == "Toyota"
    assert body["vehicle_plate_number"] == "MH12AB1234"
    assert body["driver_profile_submitted_at"]

    me_response = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me_response.status_code == 200
    assert me_response.json()["vehicle_make"] == "Toyota"


def test_passengers_cannot_access_driver_profile(client) -> None:
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Passenger Profile User",
            "email": "passenger-profile@example.com",
            "password": "Password123",
            "phone_number": "8181818181",
            "role": "passenger",
        },
    )
    assert register_response.status_code == 201

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "passenger-profile@example.com", "password": "Password123"},
    )
    assert login_response.status_code == 200

    response = client.get(
        "/api/v1/users/me/driver-profile",
        headers={"Authorization": f"Bearer {login_response.json()['access_token']}"},
    )
    assert response.status_code == 403


def test_pending_driver_cannot_publish_or_go_online(client) -> None:
    token = _register_and_login_driver(client, email="pending-driver@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    ride_response = client.post(
        "/api/v1/rides",
        headers=headers,
        json={
            "origin": "Pune",
            "destination": "Mumbai",
            "origin_latitude": 18.5204,
            "origin_longitude": 73.8567,
            "destination_latitude": 19.076,
            "destination_longitude": 72.8777,
            "departure_time": "2030-01-01T10:00:00Z",
            "available_seats": 3,
            "price_per_seat": 500,
            "vehicle_details": "White Innova",
        },
    )
    assert ride_response.status_code == 403
    assert ride_response.json()["detail"] == "Driver verification is required before publishing rides"

    presence_response = client.post(
        "/api/v1/dispatch/presence",
        headers=headers,
        json={"latitude": 18.5204, "longitude": 73.8567, "heading": 90, "is_online": True},
    )
    assert presence_response.status_code == 403
    assert presence_response.json()["detail"] == "Driver verification is required before going online or accepting ride requests"
