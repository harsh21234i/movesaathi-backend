from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from app.models.user import DriverVerificationStatus, UserRole


class DriverVerificationUpdate(BaseModel):
    vehicle_make: str | None = Field(default=None, max_length=80)
    vehicle_model: str | None = Field(default=None, max_length=80)
    vehicle_color: str | None = Field(default=None, max_length=40)
    vehicle_plate_number: str | None = Field(default=None, max_length=30)
    driver_license_number: str | None = Field(default=None, max_length=60)


class DriverVerificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    driver_verification_status: DriverVerificationStatus
    vehicle_make: str | None
    vehicle_model: str | None
    vehicle_color: str | None
    vehicle_plate_number: str | None
    driver_license_number: str | None
    driver_verification_rejection_reason: str | None
    driver_profile_submitted_at: datetime | None
    driver_profile_reviewed_at: datetime | None


class UserResponse(BaseModel):
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


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    phone_number: str | None = Field(default=None, max_length=20)
    bio: str | None = Field(default=None, max_length=1000)
