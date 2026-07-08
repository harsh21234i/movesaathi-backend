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
    amount_minor: int
    currency: str
    status: PaymentStatus
    provider: PaymentProvider
    provider_order_id: str
    provider_payment_id: str | None
    checkout_key_id: str | None = None
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime


class PaymentListResponse(BaseModel):
    items: list[PaymentResponse]


class PaymentActionResponse(BaseModel):
    payment: PaymentResponse


class PaymentWebhookEvent(BaseModel):
    provider_event_id: str = Field(min_length=1, max_length=120)
    event_type: str = Field(min_length=1, max_length=120)
    provider_payment_id: str = Field(min_length=1, max_length=120)
    provider_order_id: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)


class PaymentWebhookResponse(BaseModel):
    processed: bool
    event_id: int
    payment_id: int | None
    status: PaymentStatus | None
