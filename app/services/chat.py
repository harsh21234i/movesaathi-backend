import logging
import json

from fastapi import HTTPException, status
from redis import Redis
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.message import Message
from app.models.user import User
from app.repositories.booking import BookingRepository
from app.repositories.message import MessageRepository
from app.schemas.message import MessageCreate


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

        try:
            self.redis.publish(
                f"chat:{payload.booking_id}",
                json.dumps(
                    {
                        "id": saved.id,
                        "booking_id": saved.booking_id,
                        "sender_id": saved.sender_id,
                        "content": saved.content,
                        "message_type": saved.message_type,
                        "created_at": saved.created_at.isoformat(),
                    }
                ),
            )
        except Exception:
            self.logger.exception("Failed to publish chat event for booking_id=%s", payload.booking_id)
        return saved

    def list_messages(self, booking_id: int, current_user: User) -> list[Message]:
        self.ensure_booking_access(booking_id, current_user)
        return self.messages.list_by_booking(booking_id)
