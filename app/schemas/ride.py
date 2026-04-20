from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.ride import RideStatus
from app.schemas.user import UserResponse


class RideCreate(BaseModel):
    origin: str = Field(min_length=2, max_length=120)
    destination: str = Field(min_length=2, max_length=120)
    departure_time: datetime
    available_seats: int = Field(ge=1, le=10)
    price_per_seat: float = Field(ge=0)
    vehicle_details: str | None = Field(default=None, max_length=150)
    notes: str | None = None


class RideUpdate(BaseModel):
    origin: str = Field(min_length=2, max_length=120)
    destination: str = Field(min_length=2, max_length=120)
    departure_time: datetime
    available_seats: int = Field(ge=0, le=10)
    price_per_seat: float = Field(ge=0)
    vehicle_details: str | None = Field(default=None, max_length=150)
    notes: str | None = None


class RideSearchParams(BaseModel):
    origin: str | None = None
    destination: str | None = None
    departure_after: datetime | None = None


class RideResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    driver_id: int
    origin: str
    destination: str
    departure_time: datetime
    available_seats: int
    price_per_seat: float
    vehicle_details: str | None
    notes: str | None
    status: RideStatus
    is_active: bool


class RidePassengerSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str
    phone_number: str | None


class RideDetailResponse(RideResponse):
    driver: UserResponse
    booked_passengers: int
    passengers: list[RidePassengerSummary]
    booking_id: int | None = None
