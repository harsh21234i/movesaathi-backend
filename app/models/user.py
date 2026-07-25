from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, DateTime, Enum as SqlEnum, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class UserRole(str, Enum):
    driver = "driver"
    passenger = "passenger"


class DriverVerificationStatus(str, Enum):
    not_required = "not_required"
    pending = "pending"
    verified = "verified"
    rejected = "rejected"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    phone_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(SqlEnum(UserRole), default=UserRole.passenger, nullable=False)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    rating: Mapped[float] = mapped_column(Float, default=5.0)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    driver_verification_status: Mapped[DriverVerificationStatus] = mapped_column(
        SqlEnum(DriverVerificationStatus),
        default=DriverVerificationStatus.not_required,
        nullable=False,
    )
    vehicle_make: Mapped[str | None] = mapped_column(String(80), nullable=True)
    vehicle_model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    vehicle_color: Mapped[str | None] = mapped_column(String(40), nullable=True)
    vehicle_plate_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    driver_license_number: Mapped[str | None] = mapped_column(String(60), nullable=True)
    driver_verification_rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    driver_profile_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    driver_profile_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    rides = relationship("Ride", back_populates="driver", cascade="all, delete-orphan")
    bookings = relationship("Booking", back_populates="passenger", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="sender", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="recipient", cascade="all, delete-orphan")
    reviews_given = relationship("Review", foreign_keys="Review.reviewer_id", back_populates="reviewer")
    reviews_received = relationship("Review", foreign_keys="Review.reviewee_id", back_populates="reviewee")
    availability = relationship("DriverAvailability", back_populates="driver", uselist=False, cascade="all, delete-orphan")
