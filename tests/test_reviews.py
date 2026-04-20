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


def _create_completed_booking(client) -> tuple[int, dict[str, str], dict[str, str], int, int]:
    driver_headers = _register_and_login(client, name="Review Driver", email="review-driver@example.com", role="driver")
    passenger_headers = _register_and_login(client, name="Review Passenger", email="review-passenger@example.com", role="passenger")

    departure_time = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    ride_response = client.post(
        "/api/v1/rides",
        headers=driver_headers,
        json={
            "origin": "Pune",
            "destination": "Mumbai",
            "departure_time": departure_time,
            "available_seats": 2,
            "price_per_seat": 300,
            "vehicle_details": "Silver Baleno",
            "notes": "Evening ride",
        },
    )
    assert ride_response.status_code == 201
    ride_id = ride_response.json()["id"]
    driver_id = ride_response.json()["driver_id"]

    booking_response = client.post(
        "/api/v1/bookings",
        headers=passenger_headers,
        json={"ride_id": ride_id, "notes": "Window seat if possible"},
    )
    assert booking_response.status_code == 200
    booking_id = booking_response.json()["id"]
    passenger_id = booking_response.json()["passenger_id"]

    accept_response = client.patch(
        f"/api/v1/bookings/{booking_id}",
        headers=driver_headers,
        json={"status": "accepted"},
    )
    assert accept_response.status_code == 200

    complete_response = client.post(f"/api/v1/rides/{ride_id}/complete", headers=driver_headers)
    assert complete_response.status_code == 200

    return booking_id, driver_headers, passenger_headers, driver_id, passenger_id


def test_passenger_can_review_driver_after_completed_trip(client) -> None:
    booking_id, _, passenger_headers, driver_id, _ = _create_completed_booking(client)

    response = client.post(
        "/api/v1/reviews",
        headers=passenger_headers,
        json={
            "booking_id": booking_id,
            "reviewee_id": driver_id,
            "rating": 5,
            "comment": "Smooth coordination and on-time pickup.",
        },
    )

    assert response.status_code == 201
    assert response.json()["reviewee_id"] == driver_id
    assert response.json()["rating"] == 5


def test_review_is_rejected_before_trip_completion(client) -> None:
    driver_headers = _register_and_login(client, name="Early Driver", email="early-driver@example.com", role="driver")
    passenger_headers = _register_and_login(client, name="Early Passenger", email="early-passenger@example.com", role="passenger")

    departure_time = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    ride_response = client.post(
        "/api/v1/rides",
        headers=driver_headers,
        json={
            "origin": "Pune",
            "destination": "Mumbai",
            "departure_time": departure_time,
            "available_seats": 2,
            "price_per_seat": 300,
            "vehicle_details": "Silver Baleno",
            "notes": "Evening ride",
        },
    )
    booking_response = client.post(
        "/api/v1/bookings",
        headers=passenger_headers,
        json={"ride_id": ride_response.json()["id"], "notes": "Window seat if possible"},
    )
    assert booking_response.status_code == 200

    response = client.post(
        "/api/v1/reviews",
        headers=passenger_headers,
        json={
            "booking_id": booking_response.json()["id"],
            "reviewee_id": ride_response.json()["driver_id"],
            "rating": 4,
            "comment": "Too early",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Reviews are only allowed after a completed trip"


def test_review_rejects_duplicate_submission_from_same_reviewer(client) -> None:
    booking_id, _, passenger_headers, driver_id, _ = _create_completed_booking(client)

    first_response = client.post(
        "/api/v1/reviews",
        headers=passenger_headers,
        json={
            "booking_id": booking_id,
            "reviewee_id": driver_id,
            "rating": 5,
            "comment": "Smooth coordination and on-time pickup.",
        },
    )
    second_response = client.post(
        "/api/v1/reviews",
        headers=passenger_headers,
        json={
            "booking_id": booking_id,
            "reviewee_id": driver_id,
            "rating": 4,
            "comment": "Trying again",
        },
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == "Reviewer has already submitted feedback for this booking"


def test_review_rejects_self_review_or_wrong_participant(client) -> None:
    booking_id, driver_headers, passenger_headers, driver_id, passenger_id = _create_completed_booking(client)

    self_review = client.post(
        "/api/v1/reviews",
        headers=passenger_headers,
        json={
            "booking_id": booking_id,
            "reviewee_id": passenger_id,
            "rating": 5,
            "comment": "Reviewing myself",
        },
    )
    wrong_target = client.post(
        "/api/v1/reviews",
        headers=driver_headers,
        json={
            "booking_id": booking_id,
            "reviewee_id": driver_id,
            "rating": 5,
            "comment": "Wrong target",
        },
    )

    assert self_review.status_code == 400
    assert self_review.json()["detail"] == "Users cannot review themselves"
    assert wrong_target.status_code == 400
    assert wrong_target.json()["detail"] == "Users cannot review themselves"
