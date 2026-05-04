from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.audit_log import AuditCleanupResponse, AuditLogListResponse, AuditLogSummaryResponse
from app.services.audit_log import AuditLogService

router = APIRouter()


@router.get("/me", response_model=AuditLogListResponse)
def list_my_audit_logs(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AuditLogListResponse:
    return AuditLogService(db).list_my_audit_logs(current_user, limit=limit, offset=offset)


@router.get("/me/summary", response_model=AuditLogSummaryResponse)
def audit_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AuditLogSummaryResponse:
    return AuditLogService(db).summarize_my_audit_logs(current_user)


@router.delete("/me/cleanup", response_model=AuditCleanupResponse)
def cleanup_my_audit_logs(
    keep_days: int = Query(default=365, ge=1, le=3650),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AuditCleanupResponse:
    return AuditLogService(db).cleanup_my_audit_logs(current_user, keep_days=keep_days)
