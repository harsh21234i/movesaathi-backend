from app.models.notification import NotificationType
from app.services.notification_jobs import enqueue_notification


def test_enqueue_notification_uses_job_queue(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr("app.services.notification_jobs.job_queue.enqueue", lambda job: calls.append(job.name))

    enqueue_notification(
        session_factory=lambda: None,  # type: ignore[return-value]
        recipient_id=7,
        notification_type=NotificationType.booking_requested,
        title="New booking request",
        body="You have a request",
    )

    assert calls == ["notification:7:booking_requested"]
