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


def _create_booking(client):
    driver_headers = _register_and_login(client, name="Pay Driver", email="pay-driver@example.com", role="driver")
    passenger_headers = _register_and_login(client, name="Pay Passenger", email="pay-passenger@example.com", role="passenger")
    departure_time = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    ride = client.post(
        "/api/v1/rides",
        headers=driver_headers,
        json={
            "origin": "Pune",
            "destination": "Mumbai",
            "departure_time": departure_time,
            "available_seats": 1,
            "price_per_seat": 450,
            "vehicle_details": "White Swift",
        },
    )
    assert ride.status_code == 201
    booking = client.post("/api/v1/bookings", headers=passenger_headers, json={"ride_id": ride.json()["id"]})
    assert booking.status_code == 200
    return booking.json()["id"], passenger_headers, driver_headers


def test_passenger_can_create_and_confirm_payment(client) -> None:
    booking_id, passenger_headers, _ = _create_booking(client)

    create_response = client.post("/api/v1/payments", headers=passenger_headers, json={"booking_id": booking_id})
    assert create_response.status_code == 200
    payment = create_response.json()
    assert payment["status"] == "pending"
    assert payment["amount"] == 450
    assert payment["currency"] == "INR"
    assert payment["provider_client_secret"]

    confirm_response = client.post(f"/api/v1/payments/{payment['id']}/confirm", headers=passenger_headers)
    assert confirm_response.status_code == 200
    assert confirm_response.json()["status"] == "authorized"


def test_driver_acceptance_captures_authorized_payment(client) -> None:
    booking_id, passenger_headers, driver_headers = _create_booking(client)
    payment = client.post("/api/v1/payments", headers=passenger_headers, json={"booking_id": booking_id}).json()
    confirmed = client.post(f"/api/v1/payments/{payment['id']}/confirm", headers=passenger_headers)
    assert confirmed.status_code == 200

    accepted = client.patch(f"/api/v1/bookings/{booking_id}", headers=driver_headers, json={"status": "accepted"})
    assert accepted.status_code == 200

    payment_detail = client.get(f"/api/v1/payments/bookings/{booking_id}", headers=driver_headers)
    assert payment_detail.status_code == 200
    assert payment_detail.json()["status"] == "captured"


def test_passenger_cancel_refunds_captured_payment(client) -> None:
    booking_id, passenger_headers, driver_headers = _create_booking(client)
    payment = client.post("/api/v1/payments", headers=passenger_headers, json={"booking_id": booking_id}).json()
    client.post(f"/api/v1/payments/{payment['id']}/confirm", headers=passenger_headers)
    client.patch(f"/api/v1/bookings/{booking_id}", headers=driver_headers, json={"status": "accepted"})

    cancelled = client.patch(
        f"/api/v1/bookings/{booking_id}",
        headers=passenger_headers,
        json={"status": "cancelled_by_passenger"},
    )
    assert cancelled.status_code == 200

    payment_detail = client.get(f"/api/v1/payments/bookings/{booking_id}", headers=passenger_headers)
    assert payment_detail.status_code == 200
    assert payment_detail.json()["status"] == "refunded"


def test_only_passenger_can_create_payment_for_booking(client) -> None:
    booking_id, _, driver_headers = _create_booking(client)

    response = client.post("/api/v1/payments", headers=driver_headers, json={"booking_id": booking_id})

    assert response.status_code == 403
    assert response.json()["detail"] == "Only the passenger can pay for this booking"


def test_duplicate_payment_is_rejected(client) -> None:
    booking_id, passenger_headers, _ = _create_booking(client)

    first = client.post("/api/v1/payments", headers=passenger_headers, json={"booking_id": booking_id})
    second = client.post("/api/v1/payments", headers=passenger_headers, json={"booking_id": booking_id})

    assert first.status_code == 200
    assert second.status_code == 409


def test_payment_webhook_authorizes_payment_idempotently(client) -> None:
    booking_id, passenger_headers, _ = _create_booking(client)
    payment = client.post("/api/v1/payments", headers=passenger_headers, json={"booking_id": booking_id}).json()

    payload = {
        "provider_event_id": "evt-authorized-1",
        "event_type": "payment.authorized",
        "provider_payment_id": payment["provider_payment_id"],
        "payload": {"source": "test"},
    }

    first = client.post("/api/v1/payments/webhooks/mock", json=payload)
    second = client.post("/api/v1/payments/webhooks/mock", json=payload)

    assert first.status_code == 200
    assert first.json()["processed"] is True
    assert first.json()["status"] == "authorized"
    assert second.status_code == 200
    assert second.json()["processed"] is False
    assert second.json()["event_id"] == first.json()["event_id"]


def test_payment_webhook_can_capture_payment(client) -> None:
    booking_id, passenger_headers, _ = _create_booking(client)
    payment = client.post("/api/v1/payments", headers=passenger_headers, json={"booking_id": booking_id}).json()

    response = client.post(
        "/api/v1/payments/webhooks/mock",
        json={
            "provider_event_id": "evt-captured-1",
            "event_type": "payment.captured",
            "provider_payment_id": payment["provider_payment_id"],
            "payload": {},
        },
    )

    assert response.status_code == 200
    assert response.json()["processed"] is True
    assert response.json()["status"] == "captured"
