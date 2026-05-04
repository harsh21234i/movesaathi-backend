from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


class AuditLogRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, audit_log: AuditLog) -> AuditLog:
        self.db.add(audit_log)
        self.db.flush()
        self.db.refresh(audit_log)
        return audit_log

    def list_for_user(self, user_id: int, *, limit: int = 20, offset: int = 0) -> list[AuditLog]:
        stmt = (
            select(AuditLog)
            .where(AuditLog.actor_user_id == user_id)
            .order_by(desc(AuditLog.created_at))
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.scalars(stmt))
