import json
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from app.models.booking import BookingStatus
from app.models.payment import Payment, PaymentEvent, PaymentProvider, PaymentStatus
from app.models.user import User
from app.repositories.booking import BookingRepository
from app.repositories.payment import PaymentRepository
from app.schemas.payment import PaymentCreate, PaymentWebhookEvent, PaymentWebhookResponse
from app.services.audit_log import AuditLogService
from app.core.metrics import metrics
from app.services.payment_jobs import (
    enqueue_payment_capture_retry,
    enqueue_payment_reconciliation,
    enqueue_payment_refund_retry,
)
from app.services.payment_provider import get_payment_provider, to_minor_units


class PaymentService:
    def __init__(self, db: Session) -> None:
        self.payments = PaymentRepository(db)
        self.bookings = BookingRepository(db)
        self.audit_logs = AuditLogService(db)
        self.payment_provider = get_payment_provider()
        self.payment_session_factory = sessionmaker(
            bind=db.get_bind(),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            future=True,
        )

    def create_payment(self, payload: PaymentCreate, current_user: User) -> Payment:
        booking = self.bookings.get_by_id(payload.booking_id)
        if not booking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
        if booking.passenger_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the passenger can pay for this booking")
        if booking.status not in {BookingStatus.pending, BookingStatus.accepted}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment cannot be created for this booking state")
        if self.payments.get_by_booking_id(booking.id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Payment already exists for this booking")

        currency = payload.currency.upper()
        amount_minor = to_minor_units(booking.ride.price_per_seat, currency)
        intent = self.payment_provider.create_payment(
            amount_minor=amount_minor,
            currency=payload.currency.upper(),
            receipt=f"booking-{booking.id}",
        )
        try:
            payment = Payment(
                booking_id=booking.id,
                payer_id=current_user.id,
                amount=booking.ride.price_per_seat,
                amount_minor=amount_minor,
                currency=currency,
                provider=intent.provider,
                provider_order_id=intent.provider_order_id,
                provider_payment_id=intent.provider_payment_id,
            )
            saved = self.payments.create(payment)
            self.payments.db.commit()
            metrics.record_payment(event="payment_created")
            self.audit_logs.record(
                action="payment_created",
                actor_user_id=current_user.id,
                entity_type="payment",
                entity_id=str(saved.id),
                metadata={"booking_id": booking.id, "amount": saved.amount, "currency": saved.currency},
            )
            saved = self.payments.get_by_id(saved.id) or saved
            return self._decorate_payment(saved)
        except Exception:
            self.payments.db.rollback()
            raise

    def confirm_payment(self, payment_id: int, current_user: User) -> Payment:
        payment = self._get_accessible_payment(payment_id, current_user)
        if payment.payer_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the passenger can confirm this payment")
        if payment.status in {PaymentStatus.authorized, PaymentStatus.captured}:
            return self._decorate_payment(payment)
        if payment.status != PaymentStatus.pending:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only pending payments can be confirmed")

        try:
            snapshot = self._provider_for_payment(payment).confirm_payment(payment.provider_order_id)
            if snapshot.status == PaymentStatus.pending:
                payment.provider_payment_id = snapshot.provider_payment_id or payment.provider_payment_id
                saved = self.payments.save(payment)
                self.payments.db.commit()
                metrics.record_payment(event="payment_confirmed", outcome="pending")
                return self._decorate_payment(saved)
            if snapshot.status not in {PaymentStatus.authorized, PaymentStatus.captured}:
                payment.status = PaymentStatus.failed
                payment.failure_reason = "Provider confirmation failed"
                saved = self.payments.save(payment)
                self.payments.db.commit()
                metrics.record_payment(event="payment_confirmed", outcome="failed")
                return self._decorate_payment(saved)
            payment.status = snapshot.status
            payment.provider_payment_id = snapshot.provider_payment_id or payment.provider_payment_id
            payment.failure_reason = None
            saved = self.payments.save(payment)
            self.payments.db.commit()
            metrics.record_payment(event="payment_confirmed")
            self.audit_logs.record(
                action="payment_authorized",
                actor_user_id=current_user.id,
                entity_type="payment",
                entity_id=str(saved.id),
                metadata={"booking_id": saved.booking_id},
            )
            saved = self.payments.get_by_id(saved.id) or saved
            if saved.status == PaymentStatus.authorized and saved.booking.status == BookingStatus.accepted:
                captured = self.capture_payment_for_booking(saved.booking_id)
                if captured:
                    return self._decorate_payment(captured)
            return self._decorate_payment(saved)
        except Exception:
            self.payments.db.rollback()
            raise

    def capture_payment_for_booking(self, booking_id: int, *, commit: bool = True) -> Payment | None:
        payment = self.payments.get_by_booking_id(booking_id)
        if not payment or payment.status != PaymentStatus.authorized:
            return payment
        self._reconcile_provider_reference(payment)
        provider = self._provider_for_payment(payment)
        if not payment.provider_payment_id or not provider.capture_payment(
            payment.provider_payment_id,
            amount_minor=payment.amount_minor,
            currency=payment.currency,
        ):
            payment.failure_reason = "Provider capture failed; retry scheduled"
            saved = self.payments.save(payment)
            if commit:
                self.payments.db.commit()
            metrics.record_payment(event="payment_capture", outcome="retry_queued")
            enqueue_payment_capture_retry(session_factory=self.payment_session_factory, payment_id=payment.id)
            self.audit_logs.record(
                action="payment_capture_retry_queued",
                actor_user_id=payment.payer_id,
                entity_type="payment",
                entity_id=str(payment.id),
                metadata={"booking_id": booking_id},
                commit=commit,
            )
            return saved
        payment.status = PaymentStatus.captured
        payment.failure_reason = None
        saved = self.payments.save(payment)
        if commit:
            self.payments.db.commit()
        metrics.record_payment(event="payment_capture")
        self.audit_logs.record(
            action="payment_captured",
            actor_user_id=payment.payer_id,
            entity_type="payment",
            entity_id=str(payment.id),
            metadata={"booking_id": booking_id},
            commit=commit,
        )
        return saved

    def refund_payment_for_booking(self, booking_id: int, *, commit: bool = True) -> Payment | None:
        payment = self.payments.get_by_booking_id(booking_id)
        if not payment or payment.status not in {PaymentStatus.authorized, PaymentStatus.captured}:
            return payment
        self._reconcile_provider_reference(payment)
        provider = self._provider_for_payment(payment)
        if payment.provider_payment_id and provider.refund_payment(
            payment.provider_payment_id,
            amount_minor=payment.amount_minor,
        ):
            payment.status = PaymentStatus.refunded
            payment.failure_reason = None
        else:
            payment.failure_reason = "Provider refund failed; retry scheduled"
        saved = self.payments.save(payment)
        if commit:
            self.payments.db.commit()
        if payment.status == PaymentStatus.refunded:
            metrics.record_payment(event="payment_refund")
            self.audit_logs.record(
                action="payment_refunded",
                actor_user_id=payment.payer_id,
                entity_type="payment",
                entity_id=str(payment.id),
                metadata={"booking_id": booking_id},
                commit=commit,
            )
        else:
            metrics.record_payment(event="payment_refund", outcome="retry_queued")
            enqueue_payment_refund_retry(session_factory=self.payment_session_factory, payment_id=payment.id)
            enqueue_payment_reconciliation(session_factory=self.payment_session_factory, payment_id=payment.id)
            self.audit_logs.record(
                action="payment_refund_retry_queued",
                actor_user_id=payment.payer_id,
                entity_type="payment",
                entity_id=str(payment.id),
                metadata={"booking_id": booking_id},
                commit=commit,
            )
        return saved

    def retry_capture_payment(self, payment_id: int) -> Payment | None:
        payment = self.payments.get_by_id(payment_id)
        if not payment or payment.status != PaymentStatus.authorized:
            return payment
        self._reconcile_provider_reference(payment)
        provider = self._provider_for_payment(payment)
        if not payment.provider_payment_id or not provider.capture_payment(
            payment.provider_payment_id,
            amount_minor=payment.amount_minor,
            currency=payment.currency,
        ):
            payment.failure_reason = "Provider capture failed"
            self.payments.save(payment)
            self.payments.db.commit()
            metrics.record_payment(event="payment_capture", outcome="failed")
            raise RuntimeError(f"payment capture retry failed for payment_id={payment.id}")
        payment.status = PaymentStatus.captured
        payment.failure_reason = None
        saved = self.payments.save(payment)
        self.payments.db.commit()
        metrics.record_payment(event="payment_capture", outcome="retry_success")
        self.audit_logs.record(
            action="payment_captured",
            actor_user_id=payment.payer_id,
            entity_type="payment",
            entity_id=str(payment.id),
            metadata={"booking_id": payment.booking_id, "retry": True},
        )
        return saved

    def retry_refund_payment(self, payment_id: int) -> Payment | None:
        payment = self.payments.get_by_id(payment_id)
        if not payment or payment.status not in {PaymentStatus.authorized, PaymentStatus.captured}:
            return payment
        self._reconcile_provider_reference(payment)
        provider = self._provider_for_payment(payment)
        if not payment.provider_payment_id or not provider.refund_payment(
            payment.provider_payment_id,
            amount_minor=payment.amount_minor,
        ):
            payment.failure_reason = "Provider refund failed"
            self.payments.save(payment)
            self.payments.db.commit()
            metrics.record_payment(event="payment_refund", outcome="failed")
            raise RuntimeError(f"payment refund retry failed for payment_id={payment.id}")
        payment.status = PaymentStatus.refunded
        payment.failure_reason = None
        saved = self.payments.save(payment)
        self.payments.db.commit()
        metrics.record_payment(event="payment_refund", outcome="retry_success")
        self.audit_logs.record(
            action="payment_refunded",
            actor_user_id=payment.payer_id,
            entity_type="payment",
            entity_id=str(payment.id),
            metadata={"booking_id": payment.booking_id, "retry": True},
        )
        return saved

    def get_payment(self, payment_id: int, current_user: User) -> Payment:
        return self._decorate_payment(self._get_accessible_payment(payment_id, current_user))

    def reconcile_accessible_payment(self, payment_id: int, current_user: User) -> Payment:
        payment = self._get_accessible_payment(payment_id, current_user)
        return self.reconcile_payment(payment.id) or self._decorate_payment(payment)

    def get_booking_payment(self, booking_id: int, current_user: User) -> Payment:
        payment = self.payments.get_by_booking_id(booking_id)
        if not payment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
        return self._decorate_payment(self._ensure_payment_access(payment, current_user))

    def list_my_payments(self, current_user: User, *, limit: int = 20, offset: int = 0) -> list[Payment]:
        return [
            self._decorate_payment(payment)
            for payment in self.payments.list_for_user(current_user.id, limit=limit, offset=offset)
        ]

    def process_webhook_event(
        self,
        payload: PaymentWebhookEvent,
        *,
        provider: PaymentProvider = PaymentProvider.mock,
    ) -> PaymentWebhookResponse:
        existing_event = self.payments.get_event_by_provider_id(payload.provider_event_id)
        if existing_event:
            payment = existing_event.payment
            return PaymentWebhookResponse(
                processed=False,
                event_id=existing_event.id,
                payment_id=payment.id if payment else None,
                status=payment.status if payment else None,
            )

        payment = self.payments.get_by_provider_payment_id(payload.provider_payment_id)
        if not payment and payload.provider_order_id:
            payment = self.payments.get_by_provider_order_id(payload.provider_order_id)
        event = PaymentEvent(
            payment_id=payment.id if payment else None,
            provider=provider,
            provider_event_id=payload.provider_event_id,
            event_type=payload.event_type,
            payload_json=json.dumps(payload.payload, default=str),
        )

        try:
            saved_event = self.payments.create_event(event)
            if payment:
                payment.provider_payment_id = payload.provider_payment_id
                self._apply_webhook_transition(payment, payload.event_type)
                self.payments.save(payment)
            saved_event.processed_at = datetime.now(timezone.utc)
            self.payments.db.add(saved_event)
            self.payments.db.commit()
            if payment:
                self.audit_logs.record(
                    action="payment_webhook_processed",
                    actor_user_id=payment.payer_id,
                    entity_type="payment",
                    entity_id=str(payment.id),
                    metadata={"event_type": payload.event_type, "provider_event_id": payload.provider_event_id},
                )
            return PaymentWebhookResponse(
                processed=True,
                event_id=saved_event.id,
                payment_id=payment.id if payment else None,
                status=payment.status if payment else None,
            )
        except Exception:
            self.payments.db.rollback()
            raise

    def _get_accessible_payment(self, payment_id: int, current_user: User) -> Payment:
        payment = self.payments.get_by_id(payment_id)
        if not payment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
        return self._ensure_payment_access(payment, current_user)

    def _ensure_payment_access(self, payment: Payment, current_user: User) -> Payment:
        allowed_ids = {payment.payer_id, payment.booking.ride.driver_id}
        if current_user.id not in allowed_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Payment access denied")
        return payment

    def _apply_webhook_transition(self, payment: Payment, event_type: str) -> None:
        if event_type == "payment.authorized" and payment.status == PaymentStatus.pending:
            payment.status = PaymentStatus.authorized
            return
        if event_type == "payment.captured" and payment.status in {PaymentStatus.pending, PaymentStatus.authorized}:
            payment.status = PaymentStatus.captured
            return
        if event_type == "payment.refunded" and payment.status in {PaymentStatus.authorized, PaymentStatus.captured}:
            payment.status = PaymentStatus.refunded
            return
        if event_type == "payment.failed":
            payment.status = PaymentStatus.failed
            payment.failure_reason = "Provider reported payment failure"
            return
        if event_type in {"refund.processed", "payment.refunded"}:
            payment.status = PaymentStatus.refunded
            payment.failure_reason = None
            return
        if event_type == "refund.failed":
            payment.failure_reason = "Provider reported refund failure"

    def reconcile_payment(self, payment_id: int) -> Payment | None:
        payment = self.payments.get_by_id(payment_id)
        if not payment or payment.status in {PaymentStatus.refunded, PaymentStatus.failed, PaymentStatus.cancelled}:
            return payment
        snapshot = self._provider_for_payment(payment).reconcile_payment(payment.provider_order_id)
        payment.status = snapshot.status
        payment.provider_payment_id = snapshot.provider_payment_id or payment.provider_payment_id
        payment.failure_reason = None if snapshot.status != PaymentStatus.failed else "Provider reported payment failure"
        saved = self.payments.save(payment)
        self.payments.db.commit()
        metrics.record_payment(event="payment_reconciled", outcome=snapshot.status.value)
        if saved.status == PaymentStatus.authorized and saved.booking.status == BookingStatus.accepted:
            captured = self.capture_payment_for_booking(saved.booking_id)
            if captured:
                return self._decorate_payment(captured)
        return self._decorate_payment(saved)

    def verify_webhook_signature(self, body: bytes, signature: str, *, provider: PaymentProvider) -> bool:
        return get_payment_provider(provider).verify_webhook_signature(body, signature)

    def _reconcile_provider_reference(self, payment: Payment) -> None:
        if payment.provider_payment_id:
            return
        snapshot = self._provider_for_payment(payment).reconcile_payment(payment.provider_order_id)
        payment.provider_payment_id = snapshot.provider_payment_id
        if snapshot.status in {PaymentStatus.captured, PaymentStatus.refunded, PaymentStatus.failed}:
            payment.status = snapshot.status

    def _decorate_payment(self, payment: Payment) -> Payment:
        payment.checkout_key_id = self._provider_for_payment(payment).checkout_key_id  # type: ignore[attr-defined]
        return payment

    @staticmethod
    def _provider_for_payment(payment: Payment):
        return get_payment_provider(payment.provider)
