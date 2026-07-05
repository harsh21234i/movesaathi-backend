from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.booking import BookingStatus
from app.schemas.user import UserResponse


class BookingCreate(BaseModel):
    ride_id: int
    notes: str | None = None


class BookingStatusUpdate(BaseModel):
    status: BookingStatus


class BoardingOtpVerify(BaseModel):
    otp: str = Field(pattern=r"^\d{6}$")


class BoardingOtpResponse(BaseModel):
    otp: str
    expires_at: datetime


class BookingShareTokenResponse(BaseModel):
    token: str
    booking_id: int
    created_at: datetime


class BookingShareRevokeResponse(BaseModel):
    revoked: bool


class PublicTripDriverSummary(BaseModel):
    first_name: str
    rating: float


class PublicTripLocation(BaseModel):
    latitude: float
    longitude: float
    heading: float | None
    updated_at: datetime
    age_seconds: int
    is_stale: bool


class PublicTripStatusResponse(BaseModel):
    origin: str
    destination: str
    departure_time: datetime
    ride_status: str
    booking_status: BookingStatus
    driver: PublicTripDriverSummary
    latest_location: PublicTripLocation | None = None
    location_visible: bool


class BookingRideSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    origin: str
    destination: str
    departure_time: datetime
    price_per_seat: float
    available_seats: int
    vehicle_details: str | None


class BookingPassengerSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str
    phone_number: str | None


class BookingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ride_id: int
    passenger_id: int
    status: BookingStatus
    notes: str | None
    boarded_at: datetime | None
    created_at: datetime


class PassengerBookingResponse(BookingResponse):
    ride: BookingRideSummary


class DriverBookingResponse(BookingResponse):
    ride: BookingRideSummary
    passenger: BookingPassengerSummary


class BookingStatusEvent(BaseModel):
    label: str
    tone: str
    timestamp: datetime | None = None


class BookingDetailResponse(BookingResponse):
    ride: "RideDetailResponse"
    driver: UserResponse
    passenger: UserResponse
    status_events: list[BookingStatusEvent]


from app.schemas.ride import RideDetailResponse

BookingDetailResponse.model_rebuild()
