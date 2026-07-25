from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.incident import IncidentReport, IncidentStatus


class IncidentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, incident_id: int) -> IncidentReport | None:
        stmt = (
            select(IncidentReport)
            .options(
                joinedload(IncidentReport.reporter),
                joinedload(IncidentReport.ride),
                joinedload(IncidentReport.booking),
                joinedload(IncidentReport.ride_request),
            )
            .where(IncidentReport.id == incident_id)
        )
        return self.db.scalar(stmt)

    def list_for_reporter(self, reporter_id: int, *, limit: int = 20, offset: int = 0) -> list[IncidentReport]:
        stmt = (
            select(IncidentReport)
            .where(IncidentReport.reporter_id == reporter_id)
            .order_by(IncidentReport.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(self.db.scalars(stmt))

    def list_for_support(
        self,
        *,
        incident_status: IncidentStatus | None = None,
        reporter_id: int | None = None,
        ride_id: int | None = None,
        booking_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[IncidentReport]:
        stmt = select(IncidentReport).order_by(IncidentReport.created_at.desc())
        if incident_status:
            stmt = stmt.where(IncidentReport.status == incident_status)
        if reporter_id:
            stmt = stmt.where(IncidentReport.reporter_id == reporter_id)
        if ride_id:
            stmt = stmt.where(IncidentReport.ride_id == ride_id)
        if booking_id:
            stmt = stmt.where(IncidentReport.booking_id == booking_id)
        stmt = stmt.offset(offset).limit(limit)
        return list(self.db.scalars(stmt))

    def create(self, incident: IncidentReport) -> IncidentReport:
        self.db.add(incident)
        self.db.flush()
        self.db.refresh(incident)
        return incident

    def save(self, incident: IncidentReport) -> IncidentReport:
        self.db.add(incident)
        self.db.flush()
        self.db.refresh(incident)
        return incident
