from collections.abc import Callable

from sqlalchemy.orm import Session

from app.models.notification import NotificationType
from app.services.job_queue import Job, job_queue
from app.services.notification import NotificationService


def enqueue_notification(
    *,
    session_factory: Callable[[], Session],
    recipient_id: int,
    notification_type: NotificationType,
    title: str,
    body: str,
) -> None:
    def create_notification() -> None:
        db = session_factory()
        try:
            service = NotificationService(db)
            service.create_notification(
                recipient_id=recipient_id,
                notification_type=notification_type,
                title=title,
                body=body,
            )
            db.commit()
        finally:
            db.close()

    job_queue.enqueue(
        Job(
            name=f"notification:{recipient_id}:{notification_type.value}",
            handler=create_notification,
        )
    )
