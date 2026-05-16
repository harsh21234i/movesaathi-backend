from app.services.maintenance_jobs import enqueue_job_housekeeping, enqueue_session_cleanup


def test_enqueue_session_cleanup_uses_job_queue(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr("app.services.maintenance_jobs.job_queue.enqueue", lambda job: calls.append(job.name))

    enqueue_session_cleanup(user_id=42)

    assert calls == ["session-cleanup:42"]


def test_enqueue_job_housekeeping_can_queue_heartbeat(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr("app.services.maintenance_jobs.job_queue.enqueue", lambda job: calls.append(job.name))

    class DummyDB:
        def execute(self, *_args, **_kwargs):
            return None

        def close(self):
            return None

    enqueue_job_housekeeping(session_factory=lambda: DummyDB(), user_id=42)

    assert "session-cleanup:42" in calls
    assert "housekeeping:heartbeat" in calls
