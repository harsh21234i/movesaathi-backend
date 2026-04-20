from datetime import datetime, timedelta, timezone

from app.models.notification import Notification, NotificationType
from app.models.user import User, UserRole
from app.repositories.notification import NotificationRepository


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


def test_notification_listing_and_read_state(client) -> None:
    driver_headers = _register_and_login(client, name="Driver", email="notify-driver@example.com", role="driver")
    passenger_headers = _register_and_login(client, name="Passenger", email="notify-passenger@example.com", role="passenger")
    departure_time = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    create_ride = client.post(
        "/api/v1/rides",
        headers=driver_headers,
        json={
            "origin": "Noida",
            "destination": "Delhi",
            "departure_time": departure_time,
            "available_seats": 2,
            "price_per_seat": 100,
            "vehicle_details": "Blue WagonR",
            "notes": "Morning ride",
        },
    )
    ride_id = create_ride.json()["id"]

    create_booking = client.post(
        "/api/v1/bookings",
        headers=passenger_headers,
        json={"ride_id": ride_id, "notes": "Near gate"},
    )
    assert create_booking.status_code == 200

    notifications = client.get("/api/v1/notifications", headers=driver_headers)
    assert notifications.status_code == 200
    body = notifications.json()
    assert body["unread_count"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["type"] == "booking_requested"
    assert body["items"][0]["is_read"] is False

    mark_read = client.patch(f"/api/v1/notifications/{body['items'][0]['id']}/read", headers=driver_headers)
    assert mark_read.status_code == 200
    assert mark_read.json()["is_read"] is True

    unread_only = client.get("/api/v1/notifications", headers=driver_headers, params={"is_read": "false"})
    assert unread_only.status_code == 200
    assert unread_only.json()["unread_count"] == 0
    assert unread_only.json()["items"] == []

    mark_all = client.patch("/api/v1/notifications/read-all", headers=driver_headers)
    assert mark_all.status_code == 200
    assert mark_all.json()["updated"] == 0


def test_notification_listing_supports_type_filter_and_pagination(client) -> None:
    driver_headers = _register_and_login(client, name="Driver", email="notify-driver-two@example.com", role="driver")
    passenger_headers = _register_and_login(client, name="Passenger", email="notify-passenger-two@example.com", role="passenger")
    departure_time = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    first_ride = client.post(
        "/api/v1/rides",
        headers=driver_headers,
        json={
            "origin": "Noida",
            "destination": "Delhi",
            "departure_time": departure_time,
            "available_seats": 2,
            "price_per_seat": 100,
            "vehicle_details": "Blue WagonR",
            "notes": "Morning ride",
        },
    )
    second_ride = client.post(
        "/api/v1/rides",
        headers=driver_headers,
        json={
            "origin": "Noida",
            "destination": "Gurugram",
            "departure_time": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
            "available_seats": 2,
            "price_per_seat": 150,
            "vehicle_details": "Grey Swift",
            "notes": "Evening ride",
        },
    )
    assert first_ride.status_code == 201
    assert second_ride.status_code == 201

    first_booking = client.post(
        "/api/v1/bookings",
        headers=passenger_headers,
        json={"ride_id": first_ride.json()["id"], "notes": "Near gate"},
    )
    second_booking = client.post(
        "/api/v1/bookings",
        headers=passenger_headers,
        json={"ride_id": second_ride.json()["id"], "notes": "Near station"},
    )
    assert first_booking.status_code == 200
    assert second_booking.status_code == 200

    filtered = client.get(
        "/api/v1/notifications",
        headers=driver_headers,
        params={"notification_type": "booking_requested", "limit": 1, "offset": 0},
    )
    second_page = client.get(
        "/api/v1/notifications",
        headers=driver_headers,
        params={"notification_type": "booking_requested", "limit": 1, "offset": 1},
    )

    assert filtered.status_code == 200
    assert second_page.status_code == 200
    assert filtered.json()["unread_count"] == 2
    assert len(filtered.json()["items"]) == 1
    assert len(second_page.json()["items"]) == 1
    assert filtered.json()["items"][0]["id"] != second_page.json()["items"][0]["id"]


def test_mark_all_read_updates_more_than_one_page_of_notifications(db_session) -> None:
    user = User(
        full_name="Bulk Notify User",
        email="bulk-notify@example.com",
        phone_number="9999999999",
        hashed_password="hashed",
        role=UserRole.driver,
    )
    db_session.add(user)
    db_session.flush()

    repository = NotificationRepository(db_session)
    for index in range(1005):
        repository.create(
            Notification(
                recipient_id=user.id,
                type=NotificationType.booking_requested,
                title=f"Notification {index}",
                body="Body",
            )
        )
    db_session.commit()

    updated = repository.mark_all_read(user.id, datetime.now(timezone.utc))
    db_session.commit()

    assert updated == 1005
    assert repository.count_unread(user.id) == 0
