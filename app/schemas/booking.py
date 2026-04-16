from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.booking import BookingStatus


class BookingCreate(BaseModel):
    ride_id: int
    notes: str | None = None


class BookingStatusUpdate(BaseModel):
    status: BookingStatus


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
    created_at: datetime


class PassengerBookingResponse(BookingResponse):
    ride: BookingRideSummary


class DriverBookingResponse(BookingResponse):
    ride: BookingRideSummary
    passenger: BookingPassengerSummary
