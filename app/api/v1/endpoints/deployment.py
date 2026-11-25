from fastapi import APIRouter, Depends

from app.api.deps import require_support_auth
from app.services.deployment import (
    build_deployment_checklist_payload,
    build_deployment_preflight_payload,
    build_deployment_status_payload,
)

router = APIRouter()


@router.get("/status")
def deployment_status(_: None = Depends(require_support_auth)) -> dict[str, object]:
    return build_deployment_status_payload()


@router.get("/preflight")
def deployment_preflight(_: None = Depends(require_support_auth)) -> dict[str, object]:
    return build_deployment_preflight_payload()


@router.get("/checklist")
def deployment_checklist(_: None = Depends(require_support_auth)) -> dict[str, object]:
    return build_deployment_checklist_payload()
