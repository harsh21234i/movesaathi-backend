from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, Enum as SqlEnum, Float, ForeignKey, Index, Integer, String, UniqueConstraint
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
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(SqlEnum(PaymentStatus), default=PaymentStatus.pending, nullable=False)
    provider: Mapped[PaymentProvider] = mapped_column(SqlEnum(PaymentProvider), default=PaymentProvider.mock, nullable=False)
    provider_payment_id: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    provider_client_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    booking = relationship("Booking", back_populates="payment")
    payer = relationship("User")
