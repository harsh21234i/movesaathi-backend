from __future__ import annotations

from datetime import datetime, timedelta, timezone

import json

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.user import User
from app.repositories.audit_log import AuditLogRepository
from app.schemas.audit_log import AuditCleanupResponse, AuditLogListResponse, AuditLogSummaryResponse


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
        commit: bool = True,
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
        if commit:
            self.logs.db.commit()
        return saved

    def list_my_audit_logs(self, current_user: User, *, limit: int = 20, offset: int = 0) -> AuditLogListResponse:
        items = self.logs.list_for_user(current_user.id, limit=limit, offset=offset)
        return AuditLogListResponse(items=items)

    def list_user_audit_logs(self, current_user: User, *, user_id: int, limit: int = 20, offset: int = 0) -> AuditLogListResponse:
        if current_user.id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Audit logs can only be viewed for your own account")
        return self.list_my_audit_logs(current_user, limit=limit, offset=offset)

    def summarize_my_audit_logs(self, current_user: User, *, recent_limit: int = 10) -> AuditLogSummaryResponse:
        total = self.logs.count_for_user(current_user.id)
        by_action = self.logs.counts_by_action_for_user(current_user.id)
        by_severity = self.logs.counts_by_severity_for_user(current_user.id)
        recent_items = self.logs.list_for_user(current_user.id, limit=recent_limit, offset=0)
        return AuditLogSummaryResponse(
            total=total,
            by_action=by_action,
            by_severity=by_severity,
            recent_items=recent_items,
        )

    def purge_older_than(self, *, days: int) -> int:
        if days < 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="days must be greater than zero")
        deleted = self.logs.delete_older_than(days=days)
        self.logs.db.commit()
        return deleted

    def cleanup_my_audit_logs(self, current_user: User, *, keep_days: int = 365) -> AuditCleanupResponse:
        if keep_days < 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="keep_days must be greater than zero")
        cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
        deleted = (
            self.logs.db.query(AuditLog)
            .filter(AuditLog.actor_user_id == current_user.id)
            .filter(AuditLog.created_at < cutoff)
            .delete(synchronize_session=False)
        )
        self.logs.db.commit()
        return AuditCleanupResponse(deleted=int(deleted))
