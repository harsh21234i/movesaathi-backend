from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.payment import Payment


class PaymentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, payment: Payment) -> Payment:
        self.db.add(payment)
        self.db.flush()
        self.db.refresh(payment)
        return payment

    def save(self, payment: Payment) -> Payment:
        self.db.add(payment)
        self.db.flush()
        self.db.refresh(payment)
        return payment

    def get_by_id(self, payment_id: int) -> Payment | None:
        return self.db.get(Payment, payment_id)

    def get_by_booking_id(self, booking_id: int) -> Payment | None:
        stmt = select(Payment).where(Payment.booking_id == booking_id)
        return self.db.scalar(stmt)

    def list_for_user(self, user_id: int, *, limit: int = 20, offset: int = 0) -> list[Payment]:
        stmt = (
            select(Payment)
            .where(Payment.payer_id == user_id)
            .order_by(desc(Payment.created_at))
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.scalars(stmt))
