from app.services.job_queue import Job, job_queue


def test_job_queue_runs_inline_when_synchronous(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr("app.services.job_queue.settings.JOBS_SYNCHRONOUS", True)

    job_queue.enqueue(Job(name="inline-job", handler=lambda: calls.append("ran"), max_retries=0))

    assert calls == ["ran"]


def test_job_queue_retries_and_succeeds(monkeypatch) -> None:
    monkeypatch.setattr("app.services.job_queue.settings.JOBS_SYNCHRONOUS", True)
    monkeypatch.setattr("app.services.job_queue.settings.JOB_WORKER_RETRY_DELAY_SECONDS", 0)

    attempts = {"count": 0}

    def handler() -> None:
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise RuntimeError("retry me")

    job_queue.enqueue(Job(name="retry-job", handler=handler, max_retries=2))

    assert attempts["count"] == 2
