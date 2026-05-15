from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum as SqlEnum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class RideStatus(str, Enum):
    scheduled = "scheduled"
    full = "full"
    completed = "completed"
    cancelled = "cancelled"


class Ride(Base):
    __tablename__ = "rides"
    __table_args__ = (
        CheckConstraint("available_seats >= 0", name="ck_rides_available_seats_non_negative"),
        CheckConstraint("price_per_seat >= 0", name="ck_rides_price_per_seat_non_negative"),
        CheckConstraint("origin <> destination", name="ck_rides_origin_destination_distinct"),
        Index("ix_rides_driver_status_departure", "driver_id", "status", "departure_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    origin: Mapped[str] = mapped_column(String(120), index=True)
    destination: Mapped[str] = mapped_column(String(120), index=True)
    origin_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    origin_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    destination_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    destination_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    departure_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    available_seats: Mapped[int] = mapped_column(Integer)
    price_per_seat: Mapped[float] = mapped_column(Float)
    vehicle_details: Mapped[str | None] = mapped_column(String(150), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[RideStatus] = mapped_column(SqlEnum(RideStatus), default=RideStatus.scheduled)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    driver = relationship("User", back_populates="rides")
    bookings = relationship("Booking", back_populates="ride", cascade="all, delete-orphan")
    locations = relationship("RideLocation", back_populates="ride", cascade="all, delete-orphan")


class RideLocation(Base):
    __tablename__ = "ride_locations"
    __table_args__ = (
        CheckConstraint("latitude >= -90 AND latitude <= 90", name="ck_ride_locations_latitude_range"),
        CheckConstraint("longitude >= -180 AND longitude <= 180", name="ck_ride_locations_longitude_range"),
        Index("ix_ride_locations_ride_created", "ride_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ride_id: Mapped[int] = mapped_column(ForeignKey("rides.id", ondelete="CASCADE"), nullable=False)
    driver_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    heading: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed_kmph: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    ride = relationship("Ride", back_populates="locations")
    driver = relationship("User")
