from __future__ import annotations

import logging
import queue
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

from app.core.config import settings
from app.core.metrics import metrics


@dataclass(slots=True)
class Job:
    name: str
    handler: Callable[[], None]
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    attempts: int = 0
    max_retries: int = field(default_factory=lambda: settings.JOB_WORKER_MAX_RETRIES)


class JobQueue:
    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self._jobs: "queue.Queue[Job]" = queue.Queue()
        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._state_lock = threading.Lock()
        self._recent_events: "deque[dict[str, object]]" = deque(maxlen=25)
        self._success_total = 0
        self._retry_total = 0
        self._failed_total = 0
        self._last_error: str | None = None
        self._last_failed_job: str | None = None
        self._last_successful_job: str | None = None

    def start(self) -> None:
        if not settings.JOB_WORKER_ENABLED or settings.JOBS_SYNCHRONOUS:
            return
        if self._worker and self._worker.is_alive():
            return
        self._stop_event.clear()
        self._worker = threading.Thread(target=self._run, name="job-worker", daemon=True)
        self._worker.start()

    def stop(self) -> None:
        if not self._worker:
            return
        self._stop_event.set()
        self._jobs.put(Job(name="__stop__", handler=lambda: None, max_retries=0))
        self._worker.join(timeout=5)
        self._worker = None

    def enqueue(self, job: Job) -> None:
        self._record_event(job, status="queued")
        if settings.JOBS_SYNCHRONOUS:
            self._execute(job)
            return
        if not settings.JOB_WORKER_ENABLED:
            self._execute(job)
            return
        self._jobs.put(job)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            job = self._jobs.get()
            if job.name == "__stop__":
                self._jobs.task_done()
                break
            self._execute(job)
            self._jobs.task_done()

    def _execute(self, job: Job) -> None:
        try:
            self._record_event(job, status="running")
            job.handler()
            metrics.record_job(name=job.name, status="success")
            self._record_success(job)
        except Exception:
            job.attempts += 1
            if job.attempts <= job.max_retries:
                metrics.record_job(name=job.name, status="retry")
                self._record_retry(job)
                delay = settings.JOB_WORKER_RETRY_DELAY_SECONDS * job.attempts
                self.logger.exception(
                    "Job %s failed; retrying in %ss",
                    job.name,
                    delay,
                    extra={"job_id": job.job_id},
                )
                time.sleep(delay)
                self.enqueue(job)
                return
            metrics.record_job(name=job.name, status="failed")
            self._record_failure(job)
            self.logger.exception("Job %s failed after retries", job.name, extra={"job_id": job.job_id})

    def snapshot(self) -> dict[str, object]:
        with self._state_lock:
            recent_events = list(self._recent_events)
            maintenance_events = [
                event
                for event in recent_events
                if event["name"].startswith(("session-cleanup:", "trip-reminder-email:", "audit-log-retention:"))
            ]
            dispatch_notification_events = [
                event
                for event in recent_events
                if str(event["name"]).startswith("dispatch-notification:")
            ]
            dispatch_cleanup_events = [
                event
                for event in recent_events
                if str(event["name"]).startswith(
                    (
                        "dispatch-request-expiry:",
                        "dispatch-dismissal-cleanup:",
                        "dispatch-presence-cleanup:",
                    )
                )
            ]
            return {
                "worker_enabled": settings.JOB_WORKER_ENABLED,
                "synchronous": settings.JOBS_SYNCHRONOUS,
                "worker_running": bool(self._worker and self._worker.is_alive()),
                "queued_jobs": self._jobs.qsize(),
                "success_total": self._success_total,
                "retry_total": self._retry_total,
                "failed_total": self._failed_total,
                "last_successful_job": self._last_successful_job,
                "last_failed_job": self._last_failed_job,
                "last_error": self._last_error,
                "recent_events": recent_events,
                "maintenance_jobs": {
                    "total": len(maintenance_events),
                    "session_cleanup": sum(1 for event in maintenance_events if str(event["name"]).startswith("session-cleanup:")),
                    "trip_reminders": sum(1 for event in maintenance_events if str(event["name"]).startswith("trip-reminder-email:")),
                    "audit_retention": sum(1 for event in maintenance_events if str(event["name"]).startswith("audit-log-retention:")),
                },
                "dispatch_notification_jobs": {
                    "total": len(dispatch_notification_events),
                    "matched": sum(1 for event in dispatch_notification_events if str(event["name"]).endswith(":dispatch_matched")),
                    "cancelled": sum(1 for event in dispatch_notification_events if str(event["name"]).endswith(":dispatch_cancelled")),
                    "expired": sum(1 for event in dispatch_notification_events if str(event["name"]).endswith(":dispatch_expired")),
                    "retrying": sum(1 for event in dispatch_notification_events if event["status"] == "retry"),
                },
                "dispatch_cleanup_jobs": {
                    "total": len(dispatch_cleanup_events),
                    "request_expiry": sum(1 for event in dispatch_cleanup_events if str(event["name"]).startswith("dispatch-request-expiry:")),
                    "dismissal_cleanup": sum(1 for event in dispatch_cleanup_events if str(event["name"]).startswith("dispatch-dismissal-cleanup:")),
                    "presence_cleanup": sum(1 for event in dispatch_cleanup_events if str(event["name"]).startswith("dispatch-presence-cleanup:")),
                },
                "failed_email_jobs": [
                    event
                    for event in recent_events
                    if event["status"] == "failed" and str(event["name"]).startswith("send-")
                ],
                "failed_dispatch_notification_jobs": [
                    event
                    for event in dispatch_notification_events
                    if event["status"] == "failed"
                ],
            }

    def reset(self) -> None:
        with self._state_lock:
            self._recent_events.clear()
            self._success_total = 0
            self._retry_total = 0
            self._failed_total = 0
            self._last_error = None
            self._last_failed_job = None
            self._last_successful_job = None

        while True:
            try:
                job = self._jobs.get_nowait()
            except queue.Empty:
                break
            else:
                self._jobs.task_done()

    def _record_event(self, job: Job, *, status: str, error: str | None = None) -> None:
        with self._state_lock:
            self._recent_events.append(
                {
                    "job_id": job.job_id,
                    "name": job.name,
                    "status": status,
                    "attempts": job.attempts,
                    "max_retries": job.max_retries,
                    "error": error,
                    "timestamp": time.time(),
                }
            )

    def _record_success(self, job: Job) -> None:
        with self._state_lock:
            self._success_total += 1
            self._last_successful_job = job.name
        self._record_event(job, status="success")

    def _record_retry(self, job: Job) -> None:
        with self._state_lock:
            self._retry_total += 1
        self._record_event(job, status="retry")

    def _record_failure(self, job: Job) -> None:
        error_message = f"{job.name} failed after {job.attempts} attempts"
        with self._state_lock:
            self._failed_total += 1
            self._last_failed_job = job.name
            self._last_error = error_message
        self._record_event(job, status="failed", error=error_message)


job_queue = JobQueue()
