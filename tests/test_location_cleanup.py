from datetime import datetime, timedelta, timezone

from app.models.ride import RideLocation
from app.repositories.ride import RideRepository
from app.services.location_jobs import enqueue_location_cleanup
from app.services.ride import RideService

from tests.test_locations import _create_ride, _register_and_login


def _create_locations(client, driver_headers: dict[str, str], db_session) -> int:
    ride_id = _create_ride(client, driver_headers)
    for latitude in [18.51, 18.52]:
        response = client.post(
            f"/api/v1/rides/{ride_id}/location",
            headers=driver_headers,
            json={"latitude": latitude, "longitude": 73.86},
        )
        assert response.status_code == 200

    locations = RideRepository(db_session).list_locations(ride_id)
    assert len(locations) == 2
    locations[0].created_at = datetime.now(timezone.utc) - timedelta(days=45)
    locations[1].created_at = datetime.now(timezone.utc) - timedelta(days=2)
    db_session.commit()
    return ride_id


def test_cleanup_old_locations_removes_only_expired_records(client, db_session) -> None:
    driver_headers = _register_and_login(client, name="Cleanup Driver", email="cleanup-driver@example.com", role="driver")
    ride_id = _create_locations(client, driver_headers, db_session)

    deleted = RideService(db_session).cleanup_old_locations(retention_days=30)

    remaining = RideRepository(db_session).list_locations(ride_id)
    assert deleted == 1
    assert len(remaining) == 1
    assert remaining[0].latitude == 18.51


def test_location_cleanup_job_uses_configured_retention(client, db_session, monkeypatch) -> None:
    monkeypatch.setattr("app.services.job_queue.settings.JOBS_SYNCHRONOUS", True)
    monkeypatch.setattr("app.services.location_jobs.settings.LOCATION_RETENTION_DAYS", 30)
    driver_headers = _register_and_login(client, name="Cleanup Job Driver", email="cleanup-job-driver@example.com", role="driver")
    ride_id = _create_locations(client, driver_headers, db_session)

    enqueue_location_cleanup(session_factory=lambda: db_session)

    remaining = RideRepository(db_session).list_locations(ride_id)
    assert len(remaining) == 1


def test_cleanup_old_locations_rejects_invalid_retention(db_session) -> None:
    try:
        RideService(db_session).cleanup_old_locations(retention_days=0)
    except Exception as error:
        assert getattr(error, "status_code", None) == 400
        assert getattr(error, "detail", None) == "retention_days must be greater than zero"
    else:
        raise AssertionError("Expected invalid retention to fail")
