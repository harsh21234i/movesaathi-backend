from datetime import datetime, timezone

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session, sessionmaker

from app.models.booking import Booking
from app.models.dispatch import RideRequest
from app.models.incident import IncidentReport, IncidentStatus
from app.models.notification import NotificationType
from app.models.ride import Ride
from app.models.user import User
from app.repositories.booking import BookingRepository
from app.repositories.dispatch import DispatchRepository
from app.repositories.incident import IncidentRepository
from app.repositories.ride import RideRepository
from app.schemas.incident import IncidentCreate, IncidentStatusUpdate
from app.services.audit_log import AuditLogService
from app.services.notification_jobs import enqueue_notification
from app.services.support import SupportService


class IncidentService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.incidents = IncidentRepository(db)
        self.bookings = BookingRepository(db)
        self.rides = RideRepository(db)
        self.dispatch = DispatchRepository(db)
        self.audit_logs = AuditLogService(db)
        self.notification_session_factory = sessionmaker(
            bind=db.get_bind(),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            future=True,
        )

    def create_incident(self, payload: IncidentCreate, current_user: User) -> IncidentReport:
        self._ensure_context_access(payload, current_user)
        try:
            incident = IncidentReport(
                reporter_id=current_user.id,
                ride_id=payload.ride_id,
                booking_id=payload.booking_id,
                ride_request_id=payload.ride_request_id,
                title=payload.title,
                description=payload.description,
                severity=payload.severity,
                status=IncidentStatus.open,
            )
            saved = self.incidents.create(incident)
            self.audit_logs.record(
                action="incident_report_created",
                actor_user_id=current_user.id,
                entity_type="incident_report",
                entity_id=str(saved.id),
                severity="warning" if payload.severity.value in {"high", "emergency"} else "info",
                metadata={
                    "ride_id": saved.ride_id,
                    "booking_id": saved.booking_id,
                    "ride_request_id": saved.ride_request_id,
                    "incident_severity": saved.severity.value,
                },
                commit=False,
            )
            self.db.commit()
            return saved
        except Exception:
            self.db.rollback()
            raise

    def list_my_incidents(self, current_user: User, *, limit: int = 20, offset: int = 0) -> list[IncidentReport]:
        return self.incidents.list_for_reporter(current_user.id, limit=limit, offset=offset)

    def get_my_incident(self, incident_id: int, current_user: User) -> IncidentReport:
        incident = self.incidents.get_by_id(incident_id)
        if not incident or incident.reporter_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident report not found")
        return incident

    def list_for_support(
        self,
        *,
        request: Request,
        incident_status: IncidentStatus | None = None,
        reporter_id: int | None = None,
        ride_id: int | None = None,
        booking_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[IncidentReport]:
        SupportService(self.db)._require_support_auth(request)
        return self.incidents.list_for_support(
            incident_status=incident_status,
            reporter_id=reporter_id,
            ride_id=ride_id,
            booking_id=booking_id,
            limit=limit,
            offset=offset,
        )

    def update_support_status(
        self,
        *,
        incident_id: int,
        payload: IncidentStatusUpdate,
        request: Request,
    ) -> IncidentReport:
        SupportService(self.db)._require_support_auth(request)
        incident = self.incidents.get_by_id(incident_id)
        if not incident:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident report not found")

        try:
            incident.status = payload.status
            incident.support_notes = payload.support_notes
            incident.updated_at = datetime.now(timezone.utc)
            incident.resolved_at = (
                datetime.now(timezone.utc)
                if payload.status in {IncidentStatus.resolved, IncidentStatus.dismissed}
                else None
            )
            saved = self.incidents.save(incident)
            self.audit_logs.record(
                action=f"incident_report_{payload.status.value}",
                actor_user_id=None,
                entity_type="incident_report",
                entity_id=str(saved.id),
                metadata={"status": payload.status.value, "support_notes": payload.support_notes},
                request=request,
                commit=False,
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        self._enqueue_status_notification(saved)
        return saved

    def _ensure_context_access(self, payload: IncidentCreate, current_user: User) -> None:
        if payload.booking_id:
            booking = self.bookings.get_by_id(payload.booking_id)
            if not booking or not self._can_access_booking(booking, current_user):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
        if payload.ride_id:
            ride = self.rides.get_detail_by_id(payload.ride_id)
            if not ride or not self._can_access_ride(ride, current_user):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride not found")
        if payload.ride_request_id:
            ride_request = self.dispatch.get_ride_request(payload.ride_request_id)
            if not ride_request or not self._can_access_ride_request(ride_request, current_user):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride request not found")

    def _can_access_booking(self, booking: Booking, current_user: User) -> bool:
        return current_user.id in {booking.passenger_id, booking.ride.driver_id}

    def _can_access_ride(self, ride: Ride, current_user: User) -> bool:
        if ride.driver_id == current_user.id:
            return True
        return any(booking.passenger_id == current_user.id for booking in ride.bookings)

    def _can_access_ride_request(self, ride_request: RideRequest, current_user: User) -> bool:
        return current_user.id in {ride_request.passenger_id, ride_request.matched_driver_id}

    def _enqueue_status_notification(self, incident: IncidentReport) -> None:
        enqueue_notification(
            session_factory=self.notification_session_factory,
            recipient_id=incident.reporter_id,
            notification_type=NotificationType.incident_updated,
            title="Incident report updated",
            body=f"Your incident report is now {incident.status.value}.",
        )
