from __future__ import annotations

import json

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.user import User
from app.repositories.audit_log import AuditLogRepository
from app.schemas.audit_log import AuditLogListResponse


class AuditLogService:
    def __init__(self, db: Session) -> None:
        self.logs = AuditLogRepository(db)

    def record(
        self,
        *,
        action: str,
        actor_user_id: int | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        severity: str = "info",
        metadata: dict[str, object] | None = None,
        request: Request | None = None,
    ) -> AuditLog:
        audit_log = AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            severity=severity,
            request_id=getattr(getattr(request, "state", None), "request_id", None),
            metadata_json=json.dumps(metadata or {}, default=str) if metadata else None,
        )
        saved = self.logs.create(audit_log)
        self.logs.db.commit()
        return saved

    def list_my_audit_logs(self, current_user: User, *, limit: int = 20, offset: int = 0) -> AuditLogListResponse:
        items = self.logs.list_for_user(current_user.id, limit=limit, offset=offset)
        return AuditLogListResponse(items=items)

    def list_user_audit_logs(self, current_user: User, *, user_id: int, limit: int = 20, offset: int = 0) -> AuditLogListResponse:
        if current_user.id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Audit logs can only be viewed for your own account")
        return self.list_my_audit_logs(current_user, limit=limit, offset=offset)
