import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.payment import PaymentProvider
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


@router.post("/webhooks/razorpay", response_model=PaymentWebhookResponse)
async def razorpay_payment_webhook(
    request: Request,
    db: Session = Depends(get_db),
) -> PaymentWebhookResponse:
    raw_body = await request.body()
    signature = request.headers.get("x-razorpay-signature", "")
    service = PaymentService(db)
    if not signature or not service.verify_webhook_signature(raw_body, signature, provider=PaymentProvider.razorpay):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")

    try:
        webhook = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook payload") from exc
    entity = webhook.get("payload", {}).get("payment", {}).get("entity")
    if not entity:
        entity = webhook.get("payload", {}).get("refund", {}).get("entity", {})
    provider_payment_id = entity.get("payment_id") or entity.get("id")
    if not provider_payment_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Webhook payment identifier missing")

    payload = PaymentWebhookEvent(
        provider_event_id=request.headers.get("x-razorpay-event-id") or str(webhook.get("created_at", "")),
        event_type=str(webhook.get("event", "")),
        provider_payment_id=str(provider_payment_id),
        provider_order_id=entity.get("order_id"),
        payload=webhook,
    )
    return service.process_webhook_event(payload, provider=PaymentProvider.razorpay)


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


@router.post("/{payment_id}/reconcile", response_model=PaymentResponse)
def reconcile_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaymentResponse:
    return PaymentService(db).reconcile_accessible_payment(payment_id, current_user)
