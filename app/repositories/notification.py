from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.notification import Notification


class NotificationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, notification: Notification) -> Notification:
        self.db.add(notification)
        self.db.flush()
        self.db.refresh(notification)
        return notification

    def list_for_user(self, user_id: int) -> list[Notification]:
        stmt = (
            select(Notification)
            .where(Notification.recipient_id == user_id)
            .order_by(Notification.created_at.desc())
        )
        return list(self.db.scalars(stmt).all())

    def get_for_user(self, notification_id: int, user_id: int) -> Notification | None:
        stmt = select(Notification).where(Notification.id == notification_id, Notification.recipient_id == user_id)
        return self.db.scalar(stmt)

    def mark_all_read(self, user_id: int, read_at: datetime) -> int:
        notifications = self.list_for_user(user_id)
        updated = 0
        for notification in notifications:
            if notification.is_read:
                continue
            notification.is_read = True
            notification.read_at = read_at
            self.db.add(notification)
            updated += 1
        self.db.flush()
        return updated
