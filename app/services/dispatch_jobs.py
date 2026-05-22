from collections.abc import Callable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.dispatch import DispatchService
from app.services.job_queue import Job, job_queue


def enqueue_dispatch_request_expiry(
    *,
    session_factory: Callable[[], Session],
    limit: int = 500,
) -> None:
    def expire_requests() -> None:
        db = session_factory()
        try:
            DispatchService(db).expire_stale_open_requests(limit=limit)
        finally:
            db.close()

    job_queue.enqueue(
        Job(
            name=f"dispatch-request-expiry:{limit}",
            handler=expire_requests,
        )
    )


def enqueue_dispatch_dismissal_cleanup(
    *,
    session_factory: Callable[[], Session],
    retention_days: int = settings.DISPATCH_DISMISSAL_RETENTION_DAYS,
) -> None:
    def cleanup_dismissals() -> None:
        db = session_factory()
        try:
            DispatchService(db).cleanup_driver_request_dismissals(retention_days=retention_days)
        finally:
            db.close()

    job_queue.enqueue(
        Job(
            name=f"dispatch-dismissal-cleanup:{retention_days}d",
            handler=cleanup_dismissals,
        )
    )


def enqueue_dispatch_presence_cleanup(
    *,
    session_factory: Callable[[], Session],
    retention_hours: int = settings.DISPATCH_PRESENCE_RETENTION_HOURS,
) -> None:
    def cleanup_presence() -> None:
        db = session_factory()
        try:
            DispatchService(db).cleanup_stale_driver_availability(retention_hours=retention_hours)
        finally:
            db.close()

    job_queue.enqueue(
        Job(
            name=f"dispatch-presence-cleanup:{retention_hours}h",
            handler=cleanup_presence,
        )
    )
