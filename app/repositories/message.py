from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.message import Message


class MessageRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, message: Message) -> Message:
        self.db.add(message)
        self.db.flush()
        self.db.refresh(message)
        return message

    def list_by_booking(self, booking_id: int) -> list[Message]:
        stmt = select(Message).where(Message.booking_id == booking_id).order_by(Message.created_at)
        return list(self.db.scalars(stmt).all())

    def list_unseen_for_recipient(self, booking_id: int, recipient_id: int) -> list[Message]:
        stmt = (
            select(Message)
            .where(
                Message.booking_id == booking_id,
                Message.sender_id != recipient_id,
                Message.seen_at.is_(None),
            )
            .order_by(Message.created_at)
        )
        return list(self.db.scalars(stmt).all())

    def mark_seen(self, messages: list[Message], seen_at: datetime) -> list[Message]:
        for message in messages:
            message.seen_at = seen_at
            self.db.add(message)
        self.db.flush()
        return messages
