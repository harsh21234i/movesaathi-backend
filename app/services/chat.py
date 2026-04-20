import json
import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from redis import Redis
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.message import Message
from app.models.user import User
from app.repositories.booking import BookingRepository
from app.repositories.message import MessageRepository
from app.schemas.message import MessageCreate, MessageSeenResponse


class ChatService:
    def __init__(self, db: Session) -> None:
        self.messages = MessageRepository(db)
        self.bookings = BookingRepository(db)
        self.redis = Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
        )
        self.logger = logging.getLogger(__name__)

    def _publish(self, booking_id: int, payload: dict[str, object]) -> None:
        try:
            self.redis.publish(f"chat:{booking_id}", json.dumps(payload))
        except Exception:
            self.logger.exception("Failed to publish chat event for booking_id=%s", booking_id)

    def ensure_booking_access(self, booking_id: int, current_user: User) -> None:
        booking = self.bookings.get_by_id(booking_id)
        if not booking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
        allowed_ids = {booking.passenger_id, booking.ride.driver_id}
        if current_user.id not in allowed_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Chat access denied")

    def save_message(self, payload: MessageCreate, current_user: User) -> Message:
        self.ensure_booking_access(payload.booking_id, current_user)
        try:
            message = Message(booking_id=payload.booking_id, sender_id=current_user.id, content=payload.content)
            saved = self.messages.create(message)
            self.messages.db.commit()
        except Exception:
            self.messages.db.rollback()
            raise

        self._publish(
            payload.booking_id,
            {
                "event_type": "message",
                "message": {
                    "id": saved.id,
                    "booking_id": saved.booking_id,
                    "sender_id": saved.sender_id,
                    "content": saved.content,
                    "message_type": saved.message_type,
                    "created_at": saved.created_at.isoformat(),
                    "seen_at": saved.seen_at.isoformat() if saved.seen_at else None,
                },
            },
        )
        return saved

    def list_messages(self, booking_id: int, current_user: User) -> list[Message]:
        self.ensure_booking_access(booking_id, current_user)
        return self.messages.list_by_booking(booking_id)

    def mark_messages_seen(self, booking_id: int, current_user: User) -> MessageSeenResponse:
        self.ensure_booking_access(booking_id, current_user)
        unseen_messages = self.messages.list_unseen_for_recipient(booking_id, current_user.id)
        if not unseen_messages:
            return MessageSeenResponse(updated=0, message_ids=[], seen_at=None)

        seen_at = datetime.now(timezone.utc)
        self.messages.mark_seen(unseen_messages, seen_at)
        self.messages.db.commit()

        message_ids = [message.id for message in unseen_messages]
        self._publish(
            booking_id,
            {
                "event_type": "seen",
                "booking_id": booking_id,
                "user_id": current_user.id,
                "message_ids": message_ids,
                "seen_at": seen_at.isoformat(),
            },
        )
        return MessageSeenResponse(updated=len(message_ids), message_ids=message_ids, seen_at=seen_at)

    def publish_typing(self, booking_id: int, current_user: User, *, is_typing: bool) -> None:
        self.ensure_booking_access(booking_id, current_user)
        self._publish(
            booking_id,
            {
                "event_type": "typing",
                "booking_id": booking_id,
                "user_id": current_user.id,
                "is_typing": is_typing,
            },
        )
