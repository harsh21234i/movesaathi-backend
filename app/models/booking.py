from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import CheckConstraint, DateTime, Enum as SqlEnum, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class BookingStatus(str, Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"
    cancelled_by_passenger = "cancelled_by_passenger"
    cancelled_by_driver = "cancelled_by_driver"
    completed = "completed"


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        UniqueConstraint("ride_id", "passenger_id", name="uq_booking_ride_passenger"),
        CheckConstraint("passenger_id > 0", name="ck_bookings_passenger_id_positive"),
        Index("ix_bookings_passenger_status_created", "passenger_id", "status", "created_at"),
        Index("ix_bookings_ride_status_created", "ride_id", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ride_id: Mapped[int] = mapped_column(ForeignKey("rides.id", ondelete="CASCADE"))
    passenger_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[BookingStatus] = mapped_column(SqlEnum(BookingStatus), default=BookingStatus.pending)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    ride = relationship("Ride", back_populates="bookings")
    passenger = relationship("User", back_populates="bookings")
