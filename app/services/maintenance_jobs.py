from collections.abc import Callable

from sqlalchemy.orm import Session

from app.models.booking import Booking
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
