from fastapi import APIRouter, Depends

from app.api.deps import require_support_auth
from app.services.job_queue import job_queue

router = APIRouter()


@router.get("/status")
def jobs_status(_: None = Depends(require_support_auth)) -> dict[str, object]:
    return job_queue.snapshot()
