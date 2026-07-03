from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import DriverVerificationStatus, UserRole
from app.schemas.audit_log import AuditLogSummaryResponse


class SupportUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: EmailStr
    phone_number: str | None
    role: UserRole
    bio: str | None
    rating: float
    email_verified: bool
    email_verified_at: datetime | None
    driver_verification_status: DriverVerificationStatus
    vehicle_make: str | None
    vehicle_model: str | None
    vehicle_color: str | None
    vehicle_plate_number: str | None
    driver_license_number: str | None
    driver_verification_rejection_reason: str | None
    driver_profile_submitted_at: datetime | None
    driver_profile_reviewed_at: datetime | None
    failed_login_attempts: int
    locked_until: datetime | None
    created_at: datetime
    audit_summary: AuditLogSummaryResponse | None = None


class SupportUserSearchResponse(BaseModel):
    items: list[SupportUserResponse]


class DriverVerificationReviewRequest(BaseModel):
    status: DriverVerificationStatus
    rejection_reason: str | None = Field(default=None, max_length=1000)


class PendingDriverVerificationResponse(BaseModel):
    items: list[SupportUserResponse]
