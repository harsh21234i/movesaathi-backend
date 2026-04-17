from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from app.models.user import UserRole


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
    created_at: datetime


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    phone_number: str | None = Field(default=None, max_length=20)
    bio: str | None = Field(default=None, max_length=1000)
