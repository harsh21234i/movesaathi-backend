from fastapi import APIRouter

from app.services.deployment import (
    build_deployment_checklist_payload,
    build_deployment_preflight_payload,
    build_deployment_status_payload,
)

router = APIRouter()


@router.get("/status")
def deployment_status() -> dict[str, object]:
    return build_deployment_status_payload()


@router.get("/preflight")
def deployment_preflight() -> dict[str, object]:
    return build_deployment_preflight_payload()


@router.get("/checklist")
def deployment_checklist() -> dict[str, object]:
    return build_deployment_checklist_payload()
