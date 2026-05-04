from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.audit_log import AuditLogListResponse
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
