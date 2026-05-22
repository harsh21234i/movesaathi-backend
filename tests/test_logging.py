import json
import logging

from app.core.logging import JsonFormatter
from app.services.job_queue import Job, job_queue


def test_json_formatter_includes_context_fields() -> None:
    record = logging.LogRecord(
        name="app.request",
        level=logging.INFO,
        pathname=__file__,
        lineno=12,
        msg="request completed",
        args=(),
        exc_info=None,
    )
    record.request_id = "req-1"
    record.method = "GET"
    record.path = "/health"
    record.status_code = 200
    record.duration_ms = 1.23
    record.action = "request_matched"
    record.outcome = "success"
    record.ride_request_id = 8
    record.driver_id = 2
    record.passenger_id = 3
    record.ride_id = 4
    record.booking_id = 5
    record.cleanup_count = 1

    payload = json.loads(JsonFormatter().format(record))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "app.request"
    assert payload["request_id"] == "req-1"
    assert payload["method"] == "GET"
    assert payload["path"] == "/health"
    assert payload["status_code"] == 200
    assert payload["duration_ms"] == 1.23
    assert payload["action"] == "request_matched"
    assert payload["outcome"] == "success"
    assert payload["ride_request_id"] == 8
    assert payload["driver_id"] == 2
    assert payload["passenger_id"] == 3
    assert payload["ride_id"] == 4
    assert payload["booking_id"] == 5
    assert payload["cleanup_count"] == 1


def test_job_queue_logs_job_id(monkeypatch) -> None:
    messages: list[dict[str, object]] = []

    class DummyLogger:
        def exception(self, message, *args, **kwargs):
            messages.append(kwargs.get("extra", {}))

    monkeypatch.setattr("app.services.job_queue.settings.JOBS_SYNCHRONOUS", True)
    monkeypatch.setattr("app.services.job_queue.job_queue.logger", DummyLogger())

    def handler() -> None:
        raise RuntimeError("boom")

    job_queue.enqueue(Job(name="obs-job", handler=handler, max_retries=0))

    assert messages and "job_id" in messages[0]
