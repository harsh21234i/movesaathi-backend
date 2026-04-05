from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.message import Message


class MessageRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, message: Message) -> Message:
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message

    def list_by_booking(self, booking_id: int) -> list[Message]:
        stmt = select(Message).where(Message.booking_id == booking_id).order_by(Message.created_at)
        return list(self.db.scalars(stmt).all())
