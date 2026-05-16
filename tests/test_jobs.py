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
            "maintenance_jobs": {
                "total": 2,
                "session_cleanup": 1,
                "trip_reminders": 1,
                "audit_retention": 0,
            },
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
