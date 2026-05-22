from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, DateTime, Enum as SqlEnum, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class RideRequestStatus(str, Enum):
    open = "open"
    matched = "matched"
    cancelled = "cancelled"
    expired = "expired"


class DriverAvailability(Base):
    __tablename__ = "driver_availability"
    __table_args__ = (
        UniqueConstraint("driver_id", name="uq_driver_availability_driver_id"),
        Index("ix_driver_availability_online_updated", "is_online", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    heading: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_online: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    driver = relationship("User", back_populates="availability")


class RideRequest(Base):
    __tablename__ = "ride_requests"
    __table_args__ = (
        Index("ix_ride_requests_status_created", "status", "created_at"),
        Index("ix_ride_requests_pickup_coords", "origin_latitude", "origin_longitude"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    passenger_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    origin: Mapped[str] = mapped_column(String(120))
    destination: Mapped[str] = mapped_column(String(120))
    origin_latitude: Mapped[float] = mapped_column(Float, nullable=False)
    origin_longitude: Mapped[float] = mapped_column(Float, nullable=False)
    destination_latitude: Mapped[float] = mapped_column(Float, nullable=False)
    destination_longitude: Mapped[float] = mapped_column(Float, nullable=False)
    requested_departure_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[RideRequestStatus] = mapped_column(SqlEnum(RideRequestStatus), default=RideRequestStatus.open)
    matched_driver_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    matched_ride_id: Mapped[int | None] = mapped_column(ForeignKey("rides.id", ondelete="SET NULL"), nullable=True)
    matched_booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    passenger = relationship("User", foreign_keys=[passenger_id])
    matched_driver = relationship("User", foreign_keys=[matched_driver_id])
    matched_ride = relationship("Ride", foreign_keys=[matched_ride_id])
    matched_booking = relationship("Booking", foreign_keys=[matched_booking_id])


class DriverRequestDismissal(Base):
    __tablename__ = "driver_request_dismissals"
    __table_args__ = (
        UniqueConstraint("driver_id", "request_id", name="uq_driver_request_dismissals_driver_request"),
        Index("ix_driver_request_dismissals_request_id", "request_id"),
        Index("ix_driver_request_dismissals_driver_id", "driver_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    request_id: Mapped[int] = mapped_column(ForeignKey("ride_requests.id", ondelete="CASCADE"), nullable=False)
    dismissed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    driver = relationship("User")
    request = relationship("RideRequest")
