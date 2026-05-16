from fastapi import APIRouter

from app.services.job_queue import job_queue

router = APIRouter()


@router.get("/status")
def jobs_status() -> dict[str, object]:
    return job_queue.snapshot()
