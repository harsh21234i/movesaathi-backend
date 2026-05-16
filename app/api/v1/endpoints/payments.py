from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.payment import PaymentCreate, PaymentListResponse, PaymentResponse, PaymentWebhookEvent, PaymentWebhookResponse
from app.services.payment import PaymentService

router = APIRouter()


@router.post("", response_model=PaymentResponse)
def create_payment(
    payload: PaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaymentResponse:
    return PaymentService(db).create_payment(payload, current_user)


@router.get("/mine", response_model=PaymentListResponse)
def list_my_payments(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaymentListResponse:
    return PaymentListResponse(items=PaymentService(db).list_my_payments(current_user, limit=limit, offset=offset))


@router.get("/bookings/{booking_id}", response_model=PaymentResponse)
def get_booking_payment(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaymentResponse:
    return PaymentService(db).get_booking_payment(booking_id, current_user)


@router.post("/webhooks/mock", response_model=PaymentWebhookResponse)
def mock_payment_webhook(
    payload: PaymentWebhookEvent,
    db: Session = Depends(get_db),
) -> PaymentWebhookResponse:
    return PaymentService(db).process_webhook_event(payload)


@router.get("/{payment_id}", response_model=PaymentResponse)
def get_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaymentResponse:
    return PaymentService(db).get_payment(payment_id, current_user)


@router.post("/{payment_id}/confirm", response_model=PaymentResponse)
def confirm_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaymentResponse:
    return PaymentService(db).confirm_payment(payment_id, current_user)
