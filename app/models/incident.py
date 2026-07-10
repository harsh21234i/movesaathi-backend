from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class IncidentStatus(str, Enum):
    open = "open"
    reviewing = "reviewing"
    resolved = "resolved"
    dismissed = "dismissed"


class IncidentSeverity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    emergency = "emergency"


class IncidentReport(Base):
    __tablename__ = "incident_reports"
    __table_args__ = (
        Index("ix_incident_reports_status_created", "status", "created_at"),
        Index("ix_incident_reports_reporter_created", "reporter_id", "created_at"),
        Index("ix_incident_reports_ride_status", "ride_id", "status"),
        Index("ix_incident_reports_booking_status", "booking_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ride_id: Mapped[int | None] = mapped_column(ForeignKey("rides.id", ondelete="SET NULL"), nullable=True)
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id", ondelete="SET NULL"), nullable=True)
    ride_request_id: Mapped[int | None] = mapped_column(ForeignKey("ride_requests.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(140), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[IncidentSeverity] = mapped_column(SqlEnum(IncidentSeverity), default=IncidentSeverity.medium, nullable=False)
    status: Mapped[IncidentStatus] = mapped_column(SqlEnum(IncidentStatus), default=IncidentStatus.open, nullable=False)
    support_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    reporter = relationship("User")
    ride = relationship("Ride")
    booking = relationship("Booking")
    ride_request = relationship("RideRequest")
