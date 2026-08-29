from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_serializer


class AIRideCreateAssistantRequest(BaseModel):
    prompt: str = Field(min_length=10, max_length=1500)
    timezone: str = Field(default="Asia/Kolkata", min_length=2, max_length=64)
    locale: str = Field(default="en-IN", min_length=2, max_length=16)


class AIRideCreateDraft(BaseModel):
    origin: str | None = Field(default=None, min_length=2, max_length=120)
    destination: str | None = Field(default=None, min_length=2, max_length=120)
    departure_time: datetime | None = None
    available_seats: int | None = Field(default=None, ge=1, le=10)
    price_per_seat: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    vehicle_details: str | None = Field(default=None, max_length=150)
    notes: str | None = Field(default=None, max_length=500)
    missing_fields: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0, le=1)
    safety_notes: list[str] = Field(default_factory=list)

    @field_serializer("price_per_seat", when_used="json")
    def serialize_price_per_seat(self, value: Decimal | None) -> float | None:
        return float(value) if value is not None else None


class AIRideCreateAssistantResponse(BaseModel):
    provider: str
    model: str
    used_fallback: bool
    draft: AIRideCreateDraft


class AIRideSearchAssistantRequest(BaseModel):
    prompt: str = Field(min_length=10, max_length=1500)
    timezone: str = Field(default="Asia/Kolkata", min_length=2, max_length=64)
    locale: str = Field(default="en-IN", min_length=2, max_length=16)


class AIRideSearchFilters(BaseModel):
    origin: str | None = Field(default=None, min_length=2, max_length=120)
    destination: str | None = Field(default=None, min_length=2, max_length=120)
    departure_after: datetime | None = None
    departure_before: datetime | None = None
    seat_count: int | None = Field(default=None, ge=1, le=10)
    max_price_per_seat: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    missing_fields: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0, le=1)
    search_summary: str = Field(max_length=240)
    safety_notes: list[str] = Field(default_factory=list)

    @field_serializer("max_price_per_seat", when_used="json")
    def serialize_max_price_per_seat(self, value: Decimal | None) -> float | None:
        return float(value) if value is not None else None


class AIRideSearchAssistantResponse(BaseModel):
    provider: str
    model: str
    used_fallback: bool
    filters: AIRideSearchFilters
