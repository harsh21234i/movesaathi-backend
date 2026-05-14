from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.booking import BookingStatus
from app.models.payment import Payment, PaymentStatus
from app.models.user import User
from app.repositories.booking import BookingRepository
from app.repositories.payment import PaymentRepository
from app.schemas.payment import PaymentCreate
from app.services.audit_log import AuditLogService
from app.services.payment_provider import payment_provider


class PaymentService:
    def __init__(self, db: Session) -> None:
        self.payments = PaymentRepository(db)
        self.bookings = BookingRepository(db)
        self.audit_logs = AuditLogService(db)

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

        provider_payment_id, client_secret = payment_provider.create_payment(
            amount=booking.ride.price_per_seat,
            currency=payload.currency.upper(),
        )
        try:
            payment = Payment(
                booking_id=booking.id,
                payer_id=current_user.id,
                amount=booking.ride.price_per_seat,
                currency=payload.currency.upper(),
                provider_payment_id=provider_payment_id,
                provider_client_secret=client_secret,
            )
            saved = self.payments.create(payment)
            self.payments.db.commit()
            self.audit_logs.record(
                action="payment_created",
                actor_user_id=current_user.id,
                entity_type="payment",
                entity_id=str(saved.id),
                metadata={"booking_id": booking.id, "amount": saved.amount, "currency": saved.currency},
            )
            saved = self.payments.get_by_id(saved.id) or saved
            return saved
        except Exception:
            self.payments.db.rollback()
            raise

    def confirm_payment(self, payment_id: int, current_user: User) -> Payment:
        payment = self._get_accessible_payment(payment_id, current_user)
        if payment.payer_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the passenger can confirm this payment")
        if payment.status != PaymentStatus.pending:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only pending payments can be confirmed")

        try:
            if not payment_provider.confirm_payment(payment.provider_payment_id):
                payment.status = PaymentStatus.failed
                payment.failure_reason = "Provider confirmation failed"
                saved = self.payments.save(payment)
                self.payments.db.commit()
                return saved
            payment.status = PaymentStatus.authorized
            saved = self.payments.save(payment)
            self.payments.db.commit()
            self.audit_logs.record(
                action="payment_authorized",
                actor_user_id=current_user.id,
                entity_type="payment",
                entity_id=str(saved.id),
                metadata={"booking_id": saved.booking_id},
            )
            saved = self.payments.get_by_id(saved.id) or saved
            return saved
        except Exception:
            self.payments.db.rollback()
            raise

    def capture_payment_for_booking(self, booking_id: int, *, commit: bool = True) -> Payment | None:
        payment = self.payments.get_by_booking_id(booking_id)
        if not payment or payment.status != PaymentStatus.authorized:
            return payment
        payment.status = PaymentStatus.captured
        saved = self.payments.save(payment)
        if commit:
            self.payments.db.commit()
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
        if payment_provider.refund_payment(payment.provider_payment_id):
            payment.status = PaymentStatus.refunded
        else:
            payment.status = PaymentStatus.failed
            payment.failure_reason = "Provider refund failed"
        saved = self.payments.save(payment)
        if commit:
            self.payments.db.commit()
        self.audit_logs.record(
            action="payment_refunded",
            actor_user_id=payment.payer_id,
            entity_type="payment",
            entity_id=str(payment.id),
            metadata={"booking_id": booking_id},
            commit=commit,
        )
        return saved

    def get_payment(self, payment_id: int, current_user: User) -> Payment:
        return self._get_accessible_payment(payment_id, current_user)

    def get_booking_payment(self, booking_id: int, current_user: User) -> Payment:
        payment = self.payments.get_by_booking_id(booking_id)
        if not payment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
        return self._ensure_payment_access(payment, current_user)

    def list_my_payments(self, current_user: User, *, limit: int = 20, offset: int = 0) -> list[Payment]:
        return self.payments.list_for_user(current_user.id, limit=limit, offset=offset)

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
