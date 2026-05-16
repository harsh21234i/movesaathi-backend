from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.user import UserRole
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
    failed_login_attempts: int
    locked_until: datetime | None
    created_at: datetime
    audit_summary: AuditLogSummaryResponse | None = None


class SupportUserSearchResponse(BaseModel):
    items: list[SupportUserResponse]
