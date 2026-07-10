from sqlalchemy import desc, func, select
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

    def list_for_entity(
        self,
        *,
        entity_type: str,
        entity_id: str,
        action_prefix: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[AuditLog]:
        stmt = select(AuditLog).where(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
        if action_prefix:
            stmt = stmt.where(AuditLog.action.startswith(action_prefix))
        stmt = stmt.order_by(desc(AuditLog.created_at)).limit(limit).offset(offset)
        return list(self.db.scalars(stmt))

    def count_for_user(self, user_id: int) -> int:
        stmt = select(func.count()).select_from(AuditLog).where(AuditLog.actor_user_id == user_id)
        return int(self.db.scalar(stmt) or 0)

    def counts_by_action_for_user(self, user_id: int) -> dict[str, int]:
        stmt = (
            select(AuditLog.action, func.count())
            .where(AuditLog.actor_user_id == user_id)
            .group_by(AuditLog.action)
        )
        return {action: int(count) for action, count in self.db.execute(stmt).all()}

    def counts_by_severity_for_user(self, user_id: int) -> dict[str, int]:
        stmt = (
            select(AuditLog.severity, func.count())
            .where(AuditLog.actor_user_id == user_id)
            .group_by(AuditLog.severity)
        )
        return {severity: int(count) for severity, count in self.db.execute(stmt).all()}

    def delete_older_than(self, *, days: int) -> int:
        deleted = (
            self.db.query(AuditLog)
            .filter(AuditLog.created_at < func.datetime("now", f"-{days} days"))
            .delete(synchronize_session=False)
        )
        return int(deleted)
