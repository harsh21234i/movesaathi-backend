from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.payment import Payment, PaymentEvent


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

    def create_event(self, event: PaymentEvent) -> PaymentEvent:
        self.db.add(event)
        self.db.flush()
        self.db.refresh(event)
        return event

    def get_event_by_provider_id(self, provider_event_id: str) -> PaymentEvent | None:
        stmt = select(PaymentEvent).where(PaymentEvent.provider_event_id == provider_event_id)
        return self.db.scalar(stmt)

    def get_by_provider_payment_id(self, provider_payment_id: str) -> Payment | None:
        stmt = select(Payment).where(Payment.provider_payment_id == provider_payment_id)
        return self.db.scalar(stmt)

    def get_by_provider_order_id(self, provider_order_id: str) -> Payment | None:
        stmt = select(Payment).where(Payment.provider_order_id == provider_order_id)
        return self.db.scalar(stmt)
