from app.models.notification import NotificationType
from app.services.notification_jobs import enqueue_dispatch_notification, enqueue_notification


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


def test_enqueue_dispatch_notification_uses_dedicated_job_name_and_retries(monkeypatch) -> None:
    jobs: list[tuple[str, int]] = []
    monkeypatch.setattr(
        "app.services.notification_jobs.job_queue.enqueue",
        lambda job: jobs.append((job.name, job.max_retries)),
    )
    monkeypatch.setattr("app.services.notification_jobs.settings.DISPATCH_NOTIFICATION_MAX_RETRIES", 5)

    enqueue_dispatch_notification(
        session_factory=lambda: None,  # type: ignore[return-value]
        recipient_id=11,
        notification_type=NotificationType.dispatch_matched,
        title="Matched",
        body="Driver matched",
    )

    assert jobs == [("dispatch-notification:11:dispatch_matched", 5)]
