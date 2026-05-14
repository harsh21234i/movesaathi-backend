from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.payment import PaymentProvider, PaymentStatus


class PaymentCreate(BaseModel):
    booking_id: int
    currency: str = Field(default="INR", min_length=3, max_length=3)


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    booking_id: int
    payer_id: int
    amount: float
    currency: str
    status: PaymentStatus
    provider: PaymentProvider
    provider_payment_id: str
    provider_client_secret: str | None
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime


class PaymentListResponse(BaseModel):
    items: list[PaymentResponse]


class PaymentActionResponse(BaseModel):
    payment: PaymentResponse
