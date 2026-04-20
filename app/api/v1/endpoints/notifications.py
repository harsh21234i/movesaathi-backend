from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.notification import NotificationType
from app.models.user import User
from app.schemas.notification import NotificationListResponse, NotificationReadResponse, NotificationResponse
from app.services.notification import NotificationService

router = APIRouter()


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    is_read: bool | None = Query(default=None),
    notification_type: NotificationType | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationListResponse:
    return NotificationService(db).list_notifications(
        current_user,
        is_read=is_read,
        notification_type=notification_type,
        limit=limit,
        offset=offset,
    )


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationResponse:
    return NotificationService(db).mark_as_read(notification_id, current_user)


@router.patch("/read-all", response_model=NotificationReadResponse)
def mark_all_notifications_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationReadResponse:
    updated = NotificationService(db).mark_all_as_read(current_user)
    return NotificationReadResponse(updated=updated)
