from collections.abc import Callable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.job_queue import Job, job_queue
from app.services.ride import RideService


def enqueue_location_cleanup(
    *,
    session_factory: Callable[[], Session],
    retention_days: int | None = None,
) -> None:
    resolved_retention_days = retention_days if retention_days is not None else settings.LOCATION_RETENTION_DAYS

    def cleanup_locations() -> None:
        db = session_factory()
        try:
            RideService(db).cleanup_old_locations(retention_days=resolved_retention_days)
        finally:
            db.close()

    job_queue.enqueue(
        Job(
            name=f"location-cleanup:{resolved_retention_days}d",
            handler=cleanup_locations,
        )
    )
