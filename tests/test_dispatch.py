from datetime import datetime, timedelta, timezone

from app.models.dispatch import DriverAvailability
from app.models.booking import Booking
from app.models.ride import Ride


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


def test_passenger_can_create_request_and_driver_can_find_it(client) -> None:
    passenger_headers = _register_and_login(client, name="Passenger", email="dispatch-passenger@example.com", role="passenger")
    driver_headers = _register_and_login(client, name="Driver", email="dispatch-driver@example.com", role="driver")
    departure_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()

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
            "notes": "Need a direct trip",
        },
    )
    assert create_response.status_code == 201
    request_id = create_response.json()["id"]

    presence_response = client.post(
        "/api/v1/dispatch/presence",
        headers=driver_headers,
        json={
            "latitude": 18.6,
            "longitude": 73.8,
            "heading": 45,
            "is_online": True,
        },
    )
    assert presence_response.status_code == 201

    nearby_response = client.get("/api/v1/dispatch/requests/nearby", headers=driver_headers)
    assert nearby_response.status_code == 200
    nearby = nearby_response.json()
    assert len(nearby) == 1
    assert nearby[0]["id"] == request_id
    assert nearby[0]["distance_km"] < 25


def test_driver_accepts_request_into_private_trip(client) -> None:
    passenger_headers = _register_and_login(client, name="Passenger", email="dispatch-accept-passenger@example.com", role="passenger")
    driver_headers = _register_and_login(client, name="Driver", email="dispatch-accept-driver@example.com", role="driver")
    departure_time = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()

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
            "notes": "Airport pickup",
        },
    )
    request_id = create_response.json()["id"]

    client.post(
        "/api/v1/dispatch/presence",
        headers=driver_headers,
        json={
            "latitude": 18.6,
            "longitude": 73.8,
            "is_online": True,
        },
    )

    accept_response = client.post(f"/api/v1/dispatch/requests/{request_id}/accept", headers=driver_headers)
    assert accept_response.status_code == 200
    body = accept_response.json()
    assert body["ride_id"] > 0
    assert body["booking_id"] > 0
    assert body["estimated_price_per_seat"] >= 50
    assert body["request"]["status"] == "matched"

    booking_detail = client.get(f"/api/v1/bookings/{body['booking_id']}", headers=passenger_headers)
    assert booking_detail.status_code == 200
    assert booking_detail.json()["status"] == "accepted"

    ride_detail = client.get(f"/api/v1/rides/{body['ride_id']}", headers=passenger_headers)
    assert ride_detail.status_code == 200
    assert ride_detail.json()["booked_passengers"] == 1


def test_passenger_cannot_create_second_open_request(client) -> None:
    passenger_headers = _register_and_login(client, name="Passenger", email="dispatch-duplicate@example.com", role="passenger")
    departure_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()

    payload = {
        "origin": "Pune",
        "destination": "Nagpur",
        "origin_latitude": 18.5204,
        "origin_longitude": 73.8567,
        "destination_latitude": 21.1458,
        "destination_longitude": 79.0882,
        "requested_departure_time": departure_time,
        "notes": "Need a direct trip",
    }

    first_response = client.post("/api/v1/dispatch/requests", headers=passenger_headers, json=payload)
    assert first_response.status_code == 201

    second_response = client.post("/api/v1/dispatch/requests", headers=passenger_headers, json=payload)
    assert second_response.status_code == 400
    assert second_response.json()["detail"] == "Passenger already has an open ride request"


def test_passenger_can_cancel_open_request_and_remove_it_from_nearby_queue(client) -> None:
    passenger_headers = _register_and_login(client, name="Passenger", email="dispatch-cancel-passenger@example.com", role="passenger")
    driver_headers = _register_and_login(client, name="Driver", email="dispatch-cancel-driver@example.com", role="driver")
    departure_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()

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
            "notes": "Need a direct trip",
        },
    )
    assert create_response.status_code == 201
    request_id = create_response.json()["id"]

    presence_response = client.post(
        "/api/v1/dispatch/presence",
        headers=driver_headers,
        json={
            "latitude": 18.6,
            "longitude": 73.8,
            "is_online": True,
        },
    )
    assert presence_response.status_code == 201

    cancel_response = client.post(f"/api/v1/dispatch/requests/{request_id}/cancel", headers=passenger_headers)
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"

    nearby_response = client.get("/api/v1/dispatch/requests/nearby", headers=driver_headers)
    assert nearby_response.status_code == 200
    assert nearby_response.json() == []


def test_stale_open_requests_expire_before_nearby_listing(client) -> None:
    passenger_headers = _register_and_login(client, name="Passenger", email="dispatch-stale-passenger@example.com", role="passenger")
    driver_headers = _register_and_login(client, name="Driver", email="dispatch-stale-driver@example.com", role="driver")
    departure_time = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()

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
            "notes": "Old request",
        },
    )
    assert create_response.status_code == 201
    request_id = create_response.json()["id"]

    presence_response = client.post(
        "/api/v1/dispatch/presence",
        headers=driver_headers,
        json={
            "latitude": 18.6,
            "longitude": 73.8,
            "is_online": True,
        },
    )
    assert presence_response.status_code == 201

    nearby_response = client.get("/api/v1/dispatch/requests/nearby", headers=driver_headers)
    assert nearby_response.status_code == 200
    assert nearby_response.json() == []

    mine_response = client.get("/api/v1/dispatch/requests/mine", headers=passenger_headers)
    assert mine_response.status_code == 200
    assert mine_response.json()[0]["id"] == request_id
    assert mine_response.json()[0]["status"] == "expired"


def test_request_creation_publishes_nearby_driver_event(client, monkeypatch) -> None:
    passenger_headers = _register_and_login(client, name="Passenger", email="dispatch-publish-passenger@example.com", role="passenger")
    near_driver_headers = _register_and_login(client, name="Near Driver", email="dispatch-near-driver@example.com", role="driver")
    far_driver_headers = _register_and_login(client, name="Far Driver", email="dispatch-far-driver@example.com", role="driver")
    departure_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    driver_events: list[tuple[int, dict[str, object]]] = []

    from app.services.dispatch import DispatchService

    monkeypatch.setattr(
        DispatchService,
        "_publish_driver_event",
        lambda self, driver_id, payload: driver_events.append((driver_id, payload)),
    )

    near_presence = client.post(
        "/api/v1/dispatch/presence",
        headers=near_driver_headers,
        json={"latitude": 18.6, "longitude": 73.8, "is_online": True},
    )
    assert near_presence.status_code == 201

    far_presence = client.post(
        "/api/v1/dispatch/presence",
        headers=far_driver_headers,
        json={"latitude": 28.6139, "longitude": 77.2090, "is_online": True},
    )
    assert far_presence.status_code == 201

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
            "notes": "Need a direct trip",
        },
    )
    assert create_response.status_code == 201

    assert len(driver_events) == 1
    assert driver_events[0][0] == near_presence.json()["driver_id"]
    assert driver_events[0][1]["event_type"] == "nearby_request_created"


def test_request_acceptance_publishes_passenger_match_event(client, monkeypatch) -> None:
    passenger_headers = _register_and_login(client, name="Passenger", email="dispatch-match-passenger@example.com", role="passenger")
    driver_headers = _register_and_login(client, name="Driver", email="dispatch-match-driver@example.com", role="driver")
    departure_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    passenger_events: list[tuple[int, dict[str, object]]] = []

    from app.services.dispatch import DispatchService

    monkeypatch.setattr(
        DispatchService,
        "_publish_passenger_event",
        lambda self, passenger_id, payload: passenger_events.append((passenger_id, payload)),
    )

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
            "notes": "Airport pickup",
        },
    )
    request_id = create_response.json()["id"]
    passenger_id = create_response.json()["passenger_id"]

    presence_response = client.post(
        "/api/v1/dispatch/presence",
        headers=driver_headers,
        json={"latitude": 18.6, "longitude": 73.8, "is_online": True},
    )
    assert presence_response.status_code == 201

    accept_response = client.post(f"/api/v1/dispatch/requests/{request_id}/accept", headers=driver_headers)
    assert accept_response.status_code == 200

    assert passenger_events
    assert passenger_events[-1][0] == passenger_id
    assert passenger_events[-1][1]["event_type"] == "request_matched"

    passenger_notifications = client.get("/api/v1/notifications", headers=passenger_headers)
    assert passenger_notifications.status_code == 200
    assert passenger_notifications.json()["items"][0]["type"] == "dispatch_matched"

    driver_notifications = client.get("/api/v1/notifications", headers=driver_headers)
    assert driver_notifications.status_code == 200
    assert driver_notifications.json()["items"][0]["type"] == "dispatch_matched"


def test_request_acceptance_is_single_winner(client, db_session) -> None:
    passenger_headers = _register_and_login(client, name="Passenger", email="dispatch-single-winner-passenger@example.com", role="passenger")
    driver_one_headers = _register_and_login(client, name="Driver One", email="dispatch-single-winner-driver-one@example.com", role="driver")
    driver_two_headers = _register_and_login(client, name="Driver Two", email="dispatch-single-winner-driver-two@example.com", role="driver")
    departure_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()

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
            "notes": "Single winner dispatch",
        },
    )
    request_id = create_response.json()["id"]

    client.post(
        "/api/v1/dispatch/presence",
        headers=driver_one_headers,
        json={"latitude": 18.6, "longitude": 73.8, "is_online": True},
    )
    client.post(
        "/api/v1/dispatch/presence",
        headers=driver_two_headers,
        json={"latitude": 18.6, "longitude": 73.8, "is_online": True},
    )

    first_accept = client.post(f"/api/v1/dispatch/requests/{request_id}/accept", headers=driver_one_headers)
    assert first_accept.status_code == 200

    second_accept = client.post(f"/api/v1/dispatch/requests/{request_id}/accept", headers=driver_two_headers)
    assert second_accept.status_code == 400
    assert second_accept.json()["detail"] == "Ride request is no longer open"

    assert db_session.query(Ride).count() == 1
    assert db_session.query(Booking).count() == 1


def test_driver_decline_hides_request_only_for_that_driver(client) -> None:
    passenger_headers = _register_and_login(client, name="Passenger", email="dispatch-decline-passenger@example.com", role="passenger")
    driver_one_headers = _register_and_login(client, name="Driver One", email="dispatch-decline-driver-one@example.com", role="driver")
    driver_two_headers = _register_and_login(client, name="Driver Two", email="dispatch-decline-driver-two@example.com", role="driver")
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
            "notes": "Need a direct trip",
        },
    )
    request_id = request_response.json()["id"]

    client.post(
        "/api/v1/dispatch/presence",
        headers=driver_one_headers,
        json={"latitude": 18.6, "longitude": 73.8, "is_online": True},
    )
    client.post(
        "/api/v1/dispatch/presence",
        headers=driver_two_headers,
        json={"latitude": 18.6, "longitude": 73.8, "is_online": True},
    )

    decline_response = client.post(f"/api/v1/dispatch/requests/{request_id}/decline", headers=driver_one_headers)
    assert decline_response.status_code == 200
    assert decline_response.json()["dismissed"] is True

    driver_one_nearby = client.get("/api/v1/dispatch/requests/nearby", headers=driver_one_headers)
    assert driver_one_nearby.status_code == 200
    assert driver_one_nearby.json() == []

    driver_two_nearby = client.get("/api/v1/dispatch/requests/nearby", headers=driver_two_headers)
    assert driver_two_nearby.status_code == 200
    assert len(driver_two_nearby.json()) == 1
    assert driver_two_nearby.json()[0]["id"] == request_id

    passenger_request = client.get("/api/v1/dispatch/requests/mine", headers=passenger_headers)
    assert passenger_request.status_code == 200
    assert passenger_request.json()[0]["status"] == "open"


def test_cancelled_request_creates_dispatch_notification(client) -> None:
    passenger_headers = _register_and_login(client, name="Passenger", email="dispatch-notify-cancel-passenger@example.com", role="passenger")
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
            "notes": "Cancel and notify",
        },
    )
    request_id = request_response.json()["id"]

    cancel_response = client.post(f"/api/v1/dispatch/requests/{request_id}/cancel", headers=passenger_headers)
    assert cancel_response.status_code == 200

    notifications = client.get("/api/v1/notifications", headers=passenger_headers)
    assert notifications.status_code == 200
    assert notifications.json()["items"][0]["type"] == "dispatch_cancelled"


def test_stale_driver_presence_is_not_used_for_nearby_matching(client, db_session, monkeypatch) -> None:
    passenger_headers = _register_and_login(client, name="Passenger", email="dispatch-stale-driver-passenger@example.com", role="passenger")
    driver_headers = _register_and_login(client, name="Driver", email="dispatch-stale-driver@example.com", role="driver")
    departure_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()

    monkeypatch.setattr("app.core.config.settings.DISPATCH_PRESENCE_STALE_AFTER_SECONDS", 1)

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
            "notes": "Need a direct trip",
        },
    )
    assert create_response.status_code == 201

    presence_response = client.post(
        "/api/v1/dispatch/presence",
        headers=driver_headers,
        json={"latitude": 18.6, "longitude": 73.8, "is_online": True},
    )
    assert presence_response.status_code == 201

    availability = db_session.query(DriverAvailability).one()
    availability.updated_at = datetime.now(timezone.utc) - timedelta(seconds=10)
    db_session.commit()

    nearby_response = client.get("/api/v1/dispatch/requests/nearby", headers=driver_headers)
    assert nearby_response.status_code == 404


def test_expired_request_creates_dispatch_notification(client) -> None:
    passenger_headers = _register_and_login(client, name="Passenger", email="dispatch-expired-notify-passenger@example.com", role="passenger")
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
            "notes": "Expire and notify",
        },
    )
    assert create_response.status_code == 201

    mine_response = client.get("/api/v1/dispatch/requests/mine", headers=passenger_headers)
    assert mine_response.status_code == 200
    assert mine_response.json()[0]["status"] == "expired"

    notifications = client.get("/api/v1/notifications", headers=passenger_headers)
    assert notifications.status_code == 200
    assert notifications.json()["items"][0]["type"] == "dispatch_expired"
