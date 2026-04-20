from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.notification import Notification, NotificationType
from app.models.user import User
from app.repositories.notification import NotificationRepository
from app.schemas.notification import NotificationListResponse


class NotificationService:
    def __init__(self, db: Session) -> None:
        self.notifications = NotificationRepository(db)

    def create_notification(
        self,
        *,
        recipient_id: int,
        notification_type: NotificationType,
        title: str,
        body: str,
    ) -> Notification:
        notification = Notification(
            recipient_id=recipient_id,
            type=notification_type,
            title=title,
            body=body,
        )
        return self.notifications.create(notification)

    def list_notifications(
        self,
        current_user: User,
        *,
        is_read: bool | None = None,
        notification_type: NotificationType | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> NotificationListResponse:
        items = self.notifications.list_for_user(
            current_user.id,
            is_read=is_read,
            notification_type=notification_type,
            limit=limit,
            offset=offset,
        )
        unread_count = self.notifications.count_unread(current_user.id)
        return NotificationListResponse(items=items, unread_count=unread_count)

    def mark_as_read(self, notification_id: int, current_user: User) -> Notification:
        notification = self.notifications.get_for_user(notification_id, current_user.id)
        if not notification:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

        if not notification.is_read:
            notification.is_read = True
            notification.read_at = datetime.now(timezone.utc)
            self.notifications.db.add(notification)
            self.notifications.db.commit()
            self.notifications.db.refresh(notification)
        return notification

    def mark_all_as_read(self, current_user: User) -> int:
        updated = self.notifications.mark_all_read(current_user.id, datetime.now(timezone.utc))
        self.notifications.db.commit()
        return updated
