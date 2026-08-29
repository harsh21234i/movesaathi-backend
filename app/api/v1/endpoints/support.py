from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.support import (
    DriverVerificationListResponse,
    DriverVerificationReviewRequest,
    PendingDriverVerificationResponse,
    SupportBookingListResponse,
    SupportPaymentListResponse,
    SupportUserResponse,
    SupportUserSearchResponse,
)
from app.models.incident import IncidentStatus
from app.models.booking import BookingStatus
from app.models.payment import PaymentProvider, PaymentStatus
from app.models.user import DriverVerificationStatus
from app.schemas.incident import IncidentListResponse, IncidentResponse, IncidentStatusUpdate
from app.schemas.payment import PaymentResponse
from app.services.incident import IncidentService
from app.services.support import SupportService

router = APIRouter()


@router.get("/users/{user_id}", response_model=SupportUserResponse)
def support_get_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> SupportUserResponse:
    return SupportService(db).get_user(user_id, request)


@router.get("/users", response_model=SupportUserSearchResponse)
def support_search_users(
    request: Request,
    email: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> SupportUserSearchResponse:
    return SupportUserSearchResponse(items=SupportService(db).search_users(email=email, request=request))


@router.get("/driver-verifications", response_model=DriverVerificationListResponse)
def support_list_driver_verifications(
    request: Request,
    verification_status: DriverVerificationStatus | None = Query(default=None, alias="status"),
    email: str | None = Query(default=None),
    vehicle_plate_number: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> DriverVerificationListResponse:
    return DriverVerificationListResponse(
        items=SupportService(db).list_driver_verifications(
            request=request,
            verification_status=verification_status,
            email=email,
            vehicle_plate_number=vehicle_plate_number,
            limit=limit,
            offset=offset,
        )
    )


@router.get("/driver-verifications/pending", response_model=PendingDriverVerificationResponse)
def support_list_pending_driver_verifications(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> PendingDriverVerificationResponse:
    return PendingDriverVerificationResponse(
        items=SupportService(db).list_pending_driver_verifications(
            request=request,
            limit=limit,
            offset=offset,
        )
    )


@router.patch("/driver-verifications/{user_id}", response_model=SupportUserResponse)
def support_review_driver_verification(
    user_id: int,
    payload: DriverVerificationReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> SupportUserResponse:
    return SupportService(db).review_driver_verification(user_id=user_id, payload=payload, request=request)


@router.get("/incidents", response_model=IncidentListResponse)
def support_list_incidents(
    request: Request,
    incident_status: IncidentStatus | None = Query(default=None, alias="status"),
    reporter_id: int | None = Query(default=None),
    ride_id: int | None = Query(default=None),
    booking_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> IncidentListResponse:
    return IncidentListResponse(
        items=IncidentService(db).list_for_support(
            request=request,
            incident_status=incident_status,
            reporter_id=reporter_id,
            ride_id=ride_id,
            booking_id=booking_id,
            limit=limit,
            offset=offset,
        )
    )


@router.patch("/incidents/{incident_id}", response_model=IncidentResponse)
def support_update_incident_status(
    incident_id: int,
    payload: IncidentStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> IncidentResponse:
    return IncidentService(db).update_support_status(incident_id=incident_id, payload=payload, request=request)


@router.get("/payments", response_model=SupportPaymentListResponse)
def support_list_payments(
    request: Request,
    payment_status: PaymentStatus | None = Query(default=None, alias="status"),
    provider: PaymentProvider | None = Query(default=None),
    booking_id: int | None = Query(default=None),
    payer_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> SupportPaymentListResponse:
    return SupportPaymentListResponse(
        items=SupportService(db).list_payments(
            request=request,
            payment_status=payment_status,
            provider=provider,
            booking_id=booking_id,
            payer_id=payer_id,
            limit=limit,
            offset=offset,
        )
    )


@router.get("/bookings", response_model=SupportBookingListResponse)
def support_list_bookings(
    request: Request,
    booking_status: BookingStatus | None = Query(default=None, alias="status"),
    driver_id: int | None = Query(default=None),
    passenger_id: int | None = Query(default=None),
    ride_id: int | None = Query(default=None),
    boarded: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> SupportBookingListResponse:
    return SupportBookingListResponse(
        items=SupportService(db).list_bookings(
            request=request,
            booking_status=booking_status,
            driver_id=driver_id,
            passenger_id=passenger_id,
            ride_id=ride_id,
            boarded=boarded,
            limit=limit,
            offset=offset,
        )
    )


@router.post("/payments/{payment_id}/reconcile", response_model=PaymentResponse)
def support_reconcile_payment(
    payment_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> PaymentResponse:
    return SupportService(db).reconcile_payment(payment_id=payment_id, request=request)
