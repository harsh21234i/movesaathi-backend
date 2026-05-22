from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.dispatch import RideRequestStatus


class DriverPresenceUpsert(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    heading: float | None = Field(default=None, ge=0, le=360)
    is_online: bool = True


class DriverPresenceResponse(DriverPresenceUpsert):
    model_config = ConfigDict(from_attributes=True)

    id: int
    driver_id: int
    updated_at: datetime


class RideRequestCreate(BaseModel):
    origin: str = Field(min_length=2, max_length=120)
    destination: str = Field(min_length=2, max_length=120)
    origin_latitude: float = Field(ge=-90, le=90)
    origin_longitude: float = Field(ge=-180, le=180)
    destination_latitude: float = Field(ge=-90, le=90)
    destination_longitude: float = Field(ge=-180, le=180)
    requested_departure_time: datetime
    notes: str | None = None


class RideRequestResponse(RideRequestCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    passenger_id: int
    status: RideRequestStatus
    matched_driver_id: int | None
    matched_ride_id: int | None
    matched_booking_id: int | None
    created_at: datetime


class NearbyRideRequestResponse(RideRequestResponse):
    distance_km: float


class RequestAcceptanceResponse(BaseModel):
    request: RideRequestResponse
    ride_id: int
    booking_id: int
    estimated_price_per_seat: float
