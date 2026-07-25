from datetime import datetime, timedelta, timezone

from tests.helpers import verify_driver_by_email


def test_support_lookup_requires_token(client, monkeypatch) -> None:
    monkeypatch.setattr("app.core.config.settings.SUPPORT_API_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.SUPPORT_API_KEY", "support-secret")

    response = client.get("/api/v1/support/users/1")

    assert response.status_code == 401

    driver_verifications = client.get("/api/v1/support/driver-verifications")
    assert driver_verifications.status_code == 401

    payments = client.get("/api/v1/support/payments")
    assert payments.status_code == 401

    bookings = client.get("/api/v1/support/bookings")
    assert bookings.status_code == 401


def test_support_lookup_returns_user_with_audit_summary(client, monkeypatch) -> None:
    monkeypatch.setattr("app.core.config.settings.SUPPORT_API_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.SUPPORT_API_KEY", "support-secret")

    client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Support User",
            "email": "support-user@example.com",
            "password": "Password123",
            "phone_number": "1111111111",
            "role": "driver",
        },
    )
    headers = {"x-support-token": "support-secret"}

    response = client.get("/api/v1/support/users?email=support-user@example.com", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["items"]
    assert body["items"][0]["email"] == "support-user@example.com"
    assert body["items"][0]["audit_summary"]["total"] >= 1
    assert body["items"][0]["driver_verification_status"] == "pending"
    assert body["items"][0]["driver_verification_history"]["items"] == []


def test_support_can_list_stuck_accepted_bookings(client, monkeypatch) -> None:
    monkeypatch.setattr("app.core.config.settings.SUPPORT_API_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.SUPPORT_API_KEY", "support-secret")

    driver = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Support Booking Driver",
            "email": "support-booking-driver@example.com",
            "password": "Password123",
            "phone_number": "1111111111",
            "role": "driver",
        },
    )
    assert driver.status_code == 201
    verify_driver_by_email("support-booking-driver@example.com")
    driver_headers = {
        "Authorization": "Bearer "
        + client.post(
            "/api/v1/auth/login",
            json={"email": "support-booking-driver@example.com", "password": "Password123"},
        ).json()["access_token"]
    }
    passenger = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Support Booking Passenger",
            "email": "support-booking-passenger@example.com",
            "password": "Password123",
            "phone_number": "2222222222",
            "role": "passenger",
        },
    )
    assert passenger.status_code == 201
    passenger_headers = {
        "Authorization": "Bearer "
        + client.post(
            "/api/v1/auth/login",
            json={"email": "support-booking-passenger@example.com", "password": "Password123"},
        ).json()["access_token"]
    }
    ride = client.post(
        "/api/v1/rides",
        headers=driver_headers,
        json={
            "origin": "Pune",
            "destination": "Mumbai",
            "departure_time": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "available_seats": 1,
            "price_per_seat": 400,
            "vehicle_details": "Sedan",
        },
    )
    assert ride.status_code == 201
    booking = client.post("/api/v1/bookings", headers=passenger_headers, json={"ride_id": ride.json()["id"]})
    assert booking.status_code == 200
    accepted = client.patch(
        f"/api/v1/bookings/{booking.json()['id']}",
        headers=driver_headers,
        json={"status": "accepted"},
    )
    assert accepted.status_code == 200

    response = client.get(
        "/api/v1/support/bookings",
        headers={"x-support-token": "support-secret"},
        params={"status": "accepted", "boarded": False},
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [booking.json()["id"]]


def test_support_can_approve_driver_verification_in_realtime(client, monkeypatch) -> None:
    monkeypatch.setattr("app.core.config.settings.SUPPORT_API_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.SUPPORT_API_KEY", "support-secret")
    published: list[dict[str, object]] = []

    def capture_publish(_service, user):
        published.append(
            {
                "user_id": user.id,
                "driver_verification_status": user.driver_verification_status.value,
            }
        )

    monkeypatch.setattr("app.services.support.SupportService._publish_driver_verification_event", capture_publish)

    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Approval Driver",
            "email": "approval-driver@example.com",
            "password": "Password123",
            "phone_number": "2222222222",
            "role": "driver",
        },
    )
    assert register_response.status_code == 201
    driver_id = register_response.json()["id"]
    driver_token = client.post(
        "/api/v1/auth/login",
        json={"email": "approval-driver@example.com", "password": "Password123"},
    ).json()["access_token"]
    profile_update = client.patch(
        "/api/v1/users/me/driver-profile",
        headers={"Authorization": f"Bearer {driver_token}"},
        json={
            "vehicle_make": "Toyota",
            "vehicle_model": "Innova",
            "vehicle_color": "White",
            "vehicle_plate_number": "MH12AB1234",
            "driver_license_number": "DL-APPROVAL-123",
        },
    )
    assert profile_update.status_code == 200
    support_headers = {"x-support-token": "support-secret"}

    pending = client.get("/api/v1/support/driver-verifications/pending", headers=support_headers)
    assert pending.status_code == 200
    assert pending.json()["items"][0]["id"] == driver_id

    filtered = client.get(
        "/api/v1/support/driver-verifications",
        headers=support_headers,
        params={"status": "pending", "email": "approval-driver", "vehicle_plate_number": "MH12"},
    )
    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()["items"]] == [driver_id]

    review = client.patch(
        f"/api/v1/support/driver-verifications/{driver_id}",
        headers=support_headers,
        json={"status": "verified"},
    )

    assert review.status_code == 200
    assert review.json()["driver_verification_status"] == "verified"
    assert review.json()["driver_verification_history"]["items"][0]["action"] == "driver_verification_verified"
    assert published == [{"user_id": driver_id, "driver_verification_status": "verified"}]

    verified = client.get(
        "/api/v1/support/driver-verifications",
        headers=support_headers,
        params={"status": "verified"},
    )
    assert verified.status_code == 200
    assert [item["id"] for item in verified.json()["items"]] == [driver_id]

    notifications = client.get(
        "/api/v1/notifications",
        headers={"Authorization": f"Bearer {driver_token}"},
    )
    assert notifications.status_code == 200
    assert notifications.json()["items"][0]["type"] == "driver_verification_approved"


def test_support_rejects_driver_verification_with_reason(client, monkeypatch) -> None:
    monkeypatch.setattr("app.core.config.settings.SUPPORT_API_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.SUPPORT_API_KEY", "support-secret")
    monkeypatch.setattr("app.services.support.SupportService._publish_driver_verification_event", lambda *_args: None)

    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Rejected Driver",
            "email": "rejected-driver@example.com",
            "password": "Password123",
            "phone_number": "3333333333",
            "role": "driver",
        },
    )
    assert register_response.status_code == 201
    driver_id = register_response.json()["id"]

    missing_reason = client.patch(
        f"/api/v1/support/driver-verifications/{driver_id}",
        headers={"x-support-token": "support-secret"},
        json={"status": "rejected"},
    )
    assert missing_reason.status_code == 400

    rejected = client.patch(
        f"/api/v1/support/driver-verifications/{driver_id}",
        headers={"x-support-token": "support-secret"},
        json={"status": "rejected", "rejection_reason": "Vehicle plate photo is unreadable"},
    )

    assert rejected.status_code == 200
    assert rejected.json()["driver_verification_status"] == "rejected"
    assert rejected.json()["driver_verification_rejection_reason"] == "Vehicle plate photo is unreadable"
