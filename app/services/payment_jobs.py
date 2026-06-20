from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from app.services.job_queue import Job, job_queue


def enqueue_payment_capture_retry(*, session_factory: sessionmaker[Session], payment_id: int) -> None:
    def handler() -> None:
        from app.services.payment import PaymentService

        with session_factory() as db:
            PaymentService(db).retry_capture_payment(payment_id)

    job_queue.enqueue(
        Job(
            name=f"payment-capture-retry:{payment_id}",
            handler=handler,
        )
    )


def enqueue_payment_refund_retry(*, session_factory: sessionmaker[Session], payment_id: int) -> None:
    def handler() -> None:
        from app.services.payment import PaymentService

        with session_factory() as db:
            PaymentService(db).retry_refund_payment(payment_id)

    job_queue.enqueue(
        Job(
            name=f"payment-refund-retry:{payment_id}",
            handler=handler,
        )
    )


def enqueue_payment_reconciliation(*, session_factory: sessionmaker[Session], payment_id: int) -> None:
    def handler() -> None:
        from app.services.payment import PaymentService

        with session_factory() as db:
            PaymentService(db).reconcile_payment(payment_id)

    job_queue.enqueue(
        Job(
            name=f"payment-reconciliation:{payment_id}",
            handler=handler,
        )
    )
