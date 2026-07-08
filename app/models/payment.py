from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, Enum as SqlEnum, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class PaymentStatus(str, Enum):
    pending = "pending"
    authorized = "authorized"
    captured = "captured"
    cancelled = "cancelled"
    refunded = "refunded"
    failed = "failed"


class PaymentProvider(str, Enum):
    mock = "mock"
    razorpay = "razorpay"


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("booking_id", name="uq_payments_booking_id"),
        Index("ix_payments_user_status_created", "payer_id", "status", "created_at"),
        Index("ix_payments_booking_status", "booking_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False)
    payer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(SqlEnum(PaymentStatus), default=PaymentStatus.pending, nullable=False)
    provider: Mapped[PaymentProvider] = mapped_column(SqlEnum(PaymentProvider), default=PaymentProvider.mock, nullable=False)
    provider_order_id: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    provider_payment_id: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    booking = relationship("Booking", back_populates="payment")
    payer = relationship("User")
    events = relationship("PaymentEvent", back_populates="payment", cascade="all, delete-orphan")


class PaymentEvent(Base):
    __tablename__ = "payment_events"
    __table_args__ = (
        UniqueConstraint("provider_event_id", name="uq_payment_events_provider_event_id"),
        Index("ix_payment_events_payment_created", "payment_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id", ondelete="CASCADE"), nullable=True)
    provider: Mapped[PaymentProvider] = mapped_column(SqlEnum(PaymentProvider), default=PaymentProvider.mock, nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(120), nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    payment = relationship("Payment", back_populates="events")
