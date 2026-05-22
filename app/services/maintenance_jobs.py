from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.repositories.audit_log import AuditLogRepository
from app.repositories.booking import BookingRepository
from app.services.dispatch_jobs import (
    enqueue_dispatch_dismissal_cleanup,
    enqueue_dispatch_presence_cleanup,
    enqueue_dispatch_request_expiry,
)
from app.services.email import EmailService
from app.services.job_queue import Job, job_queue
from app.services.token_store import token_store


def enqueue_session_cleanup(*, user_id: int) -> None:
    job_queue.enqueue(
        Job(
            name=f"session-cleanup:{user_id}",
            handler=lambda: token_store.revoke_user_sessions(user_id),
        )
    )


def enqueue_job_housekeeping(
    *,
    session_factory: Callable[[], Session] | None = None,
    user_id: int | None = None,
) -> None:
    if user_id is not None:
        enqueue_session_cleanup(user_id=user_id)

    if session_factory is not None:
        def cleanup_marker() -> None:
            db = session_factory()
            try:
                db.execute("SELECT 1")
            finally:
                db.close()

        job_queue.enqueue(Job(name="housekeeping:heartbeat", handler=cleanup_marker))
        enqueue_dispatch_request_expiry(session_factory=session_factory)
        enqueue_dispatch_dismissal_cleanup(session_factory=session_factory)
        enqueue_dispatch_presence_cleanup(session_factory=session_factory)


def enqueue_trip_reminder_email(*, booking: Booking) -> None:
    def send_reminder() -> None:
        passenger = booking.passenger
        EmailService().send_email(
            to_email=passenger.email,
            subject="Trip reminder from MooveSaathi",
            text_body=(
                f"Hi {passenger.full_name},\n\n"
                f"Your trip from {booking.ride.origin} to {booking.ride.destination} departs at "
                f"{booking.ride.departure_time.isoformat()}.\n\n"
                "Please be ready a little early."
            ),
        )

    job_queue.enqueue(
        Job(
            name=f"trip-reminder-email:{booking.id}",
            handler=send_reminder,
        )
    )


def enqueue_due_trip_reminders(
    *,
    session_factory: Callable[[], Session],
    reminder_window_minutes: int = 60,
    limit: int = 100,
) -> None:
    now = datetime.now(timezone.utc)
    upper_bound = now + timedelta(minutes=reminder_window_minutes)

    db = session_factory()
    try:
        bookings = BookingRepository(db).list_accepted_departures_within(
            starts_after=now,
            ends_before=upper_bound,
            limit=limit,
        )
        for booking in bookings:
            enqueue_trip_reminder_email(booking=booking)
    finally:
        db.close()


def enqueue_audit_log_retention(
    *,
    session_factory: Callable[[], Session],
    retention_days: int = 90,
) -> None:
    def cleanup_audit_logs() -> None:
        db = session_factory()
        try:
            deleted = AuditLogRepository(db).delete_older_than(days=retention_days)
            db.commit()
            return None
        finally:
            db.close()

    job_queue.enqueue(
        Job(
            name=f"audit-log-retention:{retention_days}d",
            handler=cleanup_audit_logs,
        )
    )
