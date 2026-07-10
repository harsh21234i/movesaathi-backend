from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.incident import IncidentSeverity, IncidentStatus


class IncidentCreate(BaseModel):
    ride_id: int | None = None
    booking_id: int | None = None
    ride_request_id: int | None = None
    title: str = Field(min_length=3, max_length=140)
    description: str = Field(min_length=10, max_length=5000)
    severity: IncidentSeverity = IncidentSeverity.medium

    @model_validator(mode="after")
    def require_context(self) -> "IncidentCreate":
        if not any((self.ride_id, self.booking_id, self.ride_request_id)):
            raise ValueError("Incident must be linked to a ride, booking, or ride request")
        return self


class IncidentStatusUpdate(BaseModel):
    status: IncidentStatus
    support_notes: str | None = Field(default=None, max_length=5000)


class IncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reporter_id: int
    ride_id: int | None
    booking_id: int | None
    ride_request_id: int | None
    title: str
    description: str
    severity: IncidentSeverity
    status: IncidentStatus
    support_notes: str | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class IncidentListResponse(BaseModel):
    items: list[IncidentResponse]
