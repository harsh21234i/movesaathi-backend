from datetime import datetime, timedelta, timezone

from app.models.dispatch import DriverAvailability, DriverRequestDismissal, RideRequest, RideRequestStatus
from app.services.dispatch import DispatchService


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


def test_expire_stale_open_requests_marks_requests_expired(client, db_session) -> None:
    passenger_headers = _register_and_login(client, name="Passenger", email="dispatch-cleanup-passenger@example.com", role="passenger")
    departure_time = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()

    create_response = client.post(
        "/api/v1/dispatch/requests",
        headers=passenger_headers,
        json={
            "origin": "Pune",
            "destination": "Nagpur",
            "origin_latitude": 18.5204,
            "origin_longitude": 73.8567,
            "destination_latitude": 21.1458,
            "destination_longitude": 79.0882,
            "requested_departure_time": departure_time,
            "notes": "Cleanup expiry",
        },
    )
    assert create_response.status_code == 201

    expired = DispatchService(db_session).expire_stale_open_requests()

    assert expired == 1
    ride_request = db_session.query(RideRequest).one()
    assert ride_request.status == RideRequestStatus.expired


def test_cleanup_driver_request_dismissals_removes_old_rows(client, db_session) -> None:
    passenger_headers = _register_and_login(client, name="Passenger", email="dispatch-cleanup-dismiss-passenger@example.com", role="passenger")
    driver_headers = _register_and_login(client, name="Driver", email="dispatch-cleanup-dismiss-driver@example.com", role="driver")
    departure_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()

    request_response = client.post(
        "/api/v1/dispatch/requests",
        headers=passenger_headers,
        json={
            "origin": "Pune",
            "destination": "Nagpur",
            "origin_latitude": 18.5204,
            "origin_longitude": 73.8567,
            "destination_latitude": 21.1458,
            "destination_longitude": 79.0882,
            "requested_departure_time": departure_time,
            "notes": "Dismissal cleanup",
        },
    )
    request_id = request_response.json()["id"]

    client.post(
        "/api/v1/dispatch/presence",
        headers=driver_headers,
        json={"latitude": 18.6, "longitude": 73.8, "is_online": True},
    )
    decline_response = client.post(f"/api/v1/dispatch/requests/{request_id}/decline", headers=driver_headers)
    assert decline_response.status_code == 200

    dismissal = db_session.query(DriverRequestDismissal).one()
    dismissal.dismissed_at = datetime.now(timezone.utc) - timedelta(days=10)
    db_session.commit()

    deleted = DispatchService(db_session).cleanup_driver_request_dismissals(retention_days=1)

    assert deleted == 1
    assert db_session.query(DriverRequestDismissal).count() == 0


def test_cleanup_stale_driver_availability_removes_old_rows(client, db_session) -> None:
    driver_headers = _register_and_login(client, name="Driver", email="dispatch-cleanup-presence-driver@example.com", role="driver")

    presence_response = client.post(
        "/api/v1/dispatch/presence",
        headers=driver_headers,
        json={"latitude": 18.6, "longitude": 73.8, "is_online": True},
    )
    assert presence_response.status_code == 201

    availability = db_session.query(DriverAvailability).one()
    availability.updated_at = datetime.now(timezone.utc) - timedelta(hours=48)
    db_session.commit()

    deleted = DispatchService(db_session).cleanup_stale_driver_availability(retention_hours=24)

    assert deleted == 1
    assert db_session.query(DriverAvailability).count() == 0
