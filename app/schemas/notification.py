from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.notification import NotificationType


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: NotificationType
    title: str
    body: str
    is_read: bool
    read_at: datetime | None
    created_at: datetime


class NotificationReadResponse(BaseModel):
    updated: int


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    unread_count: int
