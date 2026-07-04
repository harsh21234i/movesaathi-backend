from app.services.job_queue import Job, job_queue


def test_job_queue_runs_inline_when_synchronous(monkeypatch) -> None:
    job_queue.reset()
    calls: list[str] = []
    monkeypatch.setattr("app.services.job_queue.settings.JOBS_SYNCHRONOUS", True)

    job_queue.enqueue(Job(name="inline-job", handler=lambda: calls.append("ran"), max_retries=0))

    assert calls == ["ran"]
    snapshot = job_queue.snapshot()
    assert snapshot["success_total"] == 1
    assert snapshot["recent_events"][-1]["status"] == "success"


def test_job_queue_retries_and_succeeds(monkeypatch) -> None:
    job_queue.reset()
    monkeypatch.setattr("app.services.job_queue.settings.JOBS_SYNCHRONOUS", True)
    monkeypatch.setattr("app.services.job_queue.settings.JOB_WORKER_RETRY_DELAY_SECONDS", 0)

    attempts = {"count": 0}

    def handler() -> None:
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise RuntimeError("retry me")

    job_queue.enqueue(Job(name="retry-job", handler=handler, max_retries=2))

    assert attempts["count"] == 2
    snapshot = job_queue.snapshot()
    assert snapshot["retry_total"] == 1
    assert snapshot["success_total"] == 1
    assert snapshot["last_successful_job"] == "retry-job"


def test_job_queue_tracks_failures(monkeypatch) -> None:
    job_queue.reset()
    monkeypatch.setattr("app.services.job_queue.settings.JOBS_SYNCHRONOUS", True)
    monkeypatch.setattr("app.services.job_queue.settings.JOB_WORKER_RETRY_DELAY_SECONDS", 0)

    def handler() -> None:
        raise RuntimeError("boom")

    job_queue.enqueue(Job(name="failed-job", handler=handler, max_retries=0))

    snapshot = job_queue.snapshot()
    assert snapshot["failed_total"] == 1
    assert snapshot["last_failed_job"] == "failed-job"
    assert snapshot["last_error"] == "failed-job failed after 1 attempts"


def test_jobs_status_endpoint_reports_snapshot(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.v1.endpoints.jobs.job_queue.snapshot",
        lambda: {
            "worker_enabled": True,
            "synchronous": True,
            "worker_running": False,
            "queued_jobs": 0,
            "success_total": 3,
            "retry_total": 1,
            "failed_total": 0,
            "last_successful_job": "notification:1:sent",
            "last_failed_job": None,
            "last_error": None,
            "recent_events": [],
            "failed_email_jobs": [],
            "failed_dispatch_notification_jobs": [],
            "maintenance_jobs": {
                "total": 2,
                "session_cleanup": 1,
                "trip_reminders": 1,
                "audit_retention": 0,
            },
            "dispatch_notification_jobs": {
                "total": 1,
                "matched": 1,
                "cancelled": 0,
                "expired": 0,
                "retrying": 0,
            },
            "dispatch_cleanup_jobs": {
                "total": 3,
                "request_expiry": 1,
                "dismissal_cleanup": 1,
                "presence_cleanup": 1,
            },
            "payment_retry_jobs": {
                "total": 2,
                "capture_retries": 1,
                "refund_retries": 1,
                "reconciliations": 0,
                "retrying": 0,
            },
            "failed_payment_jobs": [],
        },
    )

    response = client.get("/api/v1/jobs/status")

    assert response.status_code == 200
    body = response.json()
    assert body["worker_enabled"] is True
    assert body["success_total"] == 3
    assert body["retry_total"] == 1
    assert body["maintenance_jobs"]["session_cleanup"] == 1
    assert body["maintenance_jobs"]["trip_reminders"] == 1
    assert body["dispatch_notification_jobs"]["matched"] == 1
    assert body["dispatch_cleanup_jobs"]["request_expiry"] == 1
    assert body["payment_retry_jobs"]["capture_retries"] == 1


def test_job_queue_snapshot_lists_failed_email_jobs(monkeypatch) -> None:
    job_queue.reset()
    monkeypatch.setattr("app.services.job_queue.settings.JOBS_SYNCHRONOUS", True)

    def handler() -> None:
        raise RuntimeError("email failed")

    job_queue.enqueue(Job(name="send-reset-password-email:7", handler=handler, max_retries=0))

    snapshot = job_queue.snapshot()
    assert snapshot["failed_total"] == 1
    assert len(snapshot["failed_email_jobs"]) == 1
    assert snapshot["failed_email_jobs"][0]["name"] == "send-reset-password-email:7"


def test_job_queue_snapshot_lists_failed_dispatch_notification_jobs(monkeypatch) -> None:
    job_queue.reset()
    monkeypatch.setattr("app.services.job_queue.settings.JOBS_SYNCHRONOUS", True)

    def handler() -> None:
        raise RuntimeError("dispatch notification failed")

    job_queue.enqueue(Job(name="dispatch-notification:7:dispatch_matched", handler=handler, max_retries=0))

    snapshot = job_queue.snapshot()
    assert snapshot["failed_total"] == 1
    assert snapshot["dispatch_notification_jobs"]["matched"] >= 1
    assert len(snapshot["failed_dispatch_notification_jobs"]) == 1
    assert snapshot["failed_dispatch_notification_jobs"][0]["name"] == "dispatch-notification:7:dispatch_matched"


def test_job_queue_snapshot_tracks_dispatch_notification_retries(monkeypatch) -> None:
    job_queue.reset()
    monkeypatch.setattr("app.services.job_queue.settings.JOBS_SYNCHRONOUS", True)
    monkeypatch.setattr("app.services.job_queue.settings.JOB_WORKER_RETRY_DELAY_SECONDS", 0)

    attempts = {"count": 0}

    def handler() -> None:
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise RuntimeError("retry dispatch notification")

    job_queue.enqueue(Job(name="dispatch-notification:9:dispatch_expired", handler=handler, max_retries=2))

    snapshot = job_queue.snapshot()
    assert attempts["count"] == 2
    assert snapshot["retry_total"] == 1
    assert snapshot["dispatch_notification_jobs"]["expired"] >= 1
    assert snapshot["dispatch_notification_jobs"]["retrying"] >= 1


def test_job_queue_snapshot_tracks_dispatch_cleanup_jobs(monkeypatch) -> None:
    job_queue.reset()
    monkeypatch.setattr("app.services.job_queue.settings.JOBS_SYNCHRONOUS", True)

    job_queue.enqueue(Job(name="dispatch-request-expiry:500", handler=lambda: None, max_retries=0))
    job_queue.enqueue(Job(name="dispatch-dismissal-cleanup:7d", handler=lambda: None, max_retries=0))
    job_queue.enqueue(Job(name="dispatch-presence-cleanup:24h", handler=lambda: None, max_retries=0))

    snapshot = job_queue.snapshot()
    assert snapshot["dispatch_cleanup_jobs"]["total"] >= 3
    assert snapshot["dispatch_cleanup_jobs"]["request_expiry"] >= 1
    assert snapshot["dispatch_cleanup_jobs"]["dismissal_cleanup"] >= 1
    assert snapshot["dispatch_cleanup_jobs"]["presence_cleanup"] >= 1


def test_job_queue_snapshot_tracks_payment_retry_jobs(monkeypatch) -> None:
    job_queue.reset()
    monkeypatch.setattr("app.services.job_queue.settings.JOBS_SYNCHRONOUS", True)

    job_queue.enqueue(Job(name="payment-capture-retry:11", handler=lambda: None, max_retries=0))
    job_queue.enqueue(Job(name="payment-refund-retry:12", handler=lambda: None, max_retries=0))
    job_queue.enqueue(Job(name="payment-reconciliation:13", handler=lambda: None, max_retries=0))

    snapshot = job_queue.snapshot()
    assert snapshot["payment_retry_jobs"]["total"] >= 3
    assert snapshot["payment_retry_jobs"]["capture_retries"] >= 1
    assert snapshot["payment_retry_jobs"]["refund_retries"] >= 1
    assert snapshot["payment_retry_jobs"]["reconciliations"] >= 1


def test_job_queue_snapshot_lists_failed_payment_jobs(monkeypatch) -> None:
    job_queue.reset()
    monkeypatch.setattr("app.services.job_queue.settings.JOBS_SYNCHRONOUS", True)

    def handler() -> None:
        raise RuntimeError("payment retry failed")

    job_queue.enqueue(Job(name="payment-refund-retry:9", handler=handler, max_retries=0))

    snapshot = job_queue.snapshot()
    assert snapshot["failed_total"] == 1
    assert len(snapshot["failed_payment_jobs"]) == 1
    assert snapshot["failed_payment_jobs"][0]["name"] == "payment-refund-retry:9"
