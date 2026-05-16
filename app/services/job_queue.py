from __future__ import annotations

import logging
import queue
import threading
import time
import uuid
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
            job.handler()
            metrics.record_job(name=job.name, status="success")
        except Exception:
            job.attempts += 1
            if job.attempts <= job.max_retries:
                metrics.record_job(name=job.name, status="retry")
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
            self.logger.exception("Job %s failed after retries", job.name, extra={"job_id": job.job_id})


job_queue = JobQueue()
