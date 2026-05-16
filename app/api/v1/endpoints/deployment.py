from fastapi import APIRouter

from app.services.deployment import build_deployment_status_payload

router = APIRouter()


@router.get("/status")
def deployment_status() -> dict[str, object]:
    return build_deployment_status_payload()
