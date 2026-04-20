from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.notification import NotificationReadResponse, NotificationResponse
from app.services.notification import NotificationService

router = APIRouter()


@router.get("", response_model=list[NotificationResponse])
def list_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[NotificationResponse]:
    return NotificationService(db).list_notifications(current_user)


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
