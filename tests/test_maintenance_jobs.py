from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.maintenance_jobs import (
    enqueue_audit_log_retention,
    enqueue_due_trip_reminders,
    enqueue_job_housekeeping,
    enqueue_session_cleanup,
    enqueue_trip_reminder_email,
)
from tests.conftest import TestingSessionLocal
from tests.test_bookings import _create_ride, _register_and_login


def test_enqueue_session_cleanup_uses_job_queue(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr("app.services.maintenance_jobs.job_queue.enqueue", lambda job: calls.append(job.name))

    enqueue_session_cleanup(user_id=42)

    assert calls == ["session-cleanup:42"]


def test_enqueue_job_housekeeping_can_queue_heartbeat(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr("app.services.maintenance_jobs.job_queue.enqueue", lambda job: calls.append(job.name))

    class DummyDB:
        def execute(self, *_args, **_kwargs):
            return None

        def close(self):
            return None

    enqueue_job_housekeeping(session_factory=lambda: DummyDB(), user_id=42)

    assert "session-cleanup:42" in calls
    assert "housekeeping:heartbeat" in calls


def test_enqueue_trip_reminder_email_uses_job_queue(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr("app.services.maintenance_jobs.job_queue.enqueue", lambda job: calls.append(job.name))

    booking = SimpleNamespace(
        id=9,
        passenger=SimpleNamespace(email="passenger@example.com", full_name="Passenger"),
        ride=SimpleNamespace(
            origin="Noida",
            destination="Delhi",
            departure_time=SimpleNamespace(isoformat=lambda: "2026-05-17T10:00:00+05:30"),
        ),
    )

    enqueue_trip_reminder_email(booking=booking)

    assert calls == ["trip-reminder-email:9"]


def test_enqueue_due_trip_reminders_only_queues_imminent_bookings(client, monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr("app.services.maintenance_jobs.job_queue.enqueue", lambda job: calls.append(job.name))

    driver_headers = _register_and_login(client, name="Reminder Driver", email="reminder-driver@example.com", role="driver")
    passenger_headers = _register_and_login(client, name="Reminder Passenger", email="reminder-passenger@example.com", role="passenger")
    later_passenger_headers = _register_and_login(
        client,
        name="Later Passenger",
        email="later-passenger@example.com",
        role="passenger",
    )

    near_departure = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
    far_departure = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    near_ride = client.post(
        "/api/v1/rides",
        headers=driver_headers,
        json={
            "origin": "Noida",
            "destination": "Delhi",
            "departure_time": near_departure,
            "available_seats": 2,
            "price_per_seat": 150,
        },
    )
    assert near_ride.status_code == 201

    far_ride = client.post(
        "/api/v1/rides",
        headers=driver_headers,
        json={
            "origin": "Agra",
            "destination": "Delhi",
            "departure_time": far_departure,
            "available_seats": 2,
            "price_per_seat": 150,
        },
    )
    assert far_ride.status_code == 201

    near_booking = client.post("/api/v1/bookings", headers=passenger_headers, json={"ride_id": near_ride.json()["id"]})
    far_booking = client.post("/api/v1/bookings", headers=later_passenger_headers, json={"ride_id": far_ride.json()["id"]})
    assert near_booking.status_code == 200
    assert far_booking.status_code == 200

    client.patch(
        f"/api/v1/bookings/{near_booking.json()['id']}",
        headers=driver_headers,
        json={"status": "accepted"},
    )
    client.patch(
        f"/api/v1/bookings/{far_booking.json()['id']}",
        headers=driver_headers,
        json={"status": "accepted"},
    )

    enqueue_due_trip_reminders(session_factory=lambda: TestingSessionLocal(), reminder_window_minutes=60)

    assert any(name.startswith("trip-reminder-email:") for name in calls)
    assert len([name for name in calls if name.startswith("trip-reminder-email:")]) == 1


def test_enqueue_audit_log_retention_uses_job_queue(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr("app.services.maintenance_jobs.job_queue.enqueue", lambda job: calls.append(job.name))

    class DummyDB:
        def commit(self):
            return None

        def close(self):
            return None

    enqueue_audit_log_retention(session_factory=lambda: DummyDB(), retention_days=90)

    assert calls == ["audit-log-retention:90d"]
