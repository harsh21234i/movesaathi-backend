from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.api.idempotency import idempotent_execute
from app.core.config import settings
from app.core.rate_limit import rate_limit_dependency
from app.models.booking import BookingStatus
from app.models.user import User
from app.schemas.booking import (
    BookingCreate,
    BoardingOtpResponse,
    BoardingOtpVerify,
    BookingDetailResponse,
    BookingResponse,
    BookingStatusUpdate,
    DriverBookingResponse,
    PassengerBookingResponse,
)
from app.services.booking import BookingService

router = APIRouter()


@router.post("", response_model=BookingResponse)
async def create_booking(
    payload: BookingCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(
        rate_limit_dependency(
            "booking-write",
            limit=lambda: settings.BOOKING_WRITE_RATE_LIMIT_MAX_REQUESTS,
            window_seconds=lambda: settings.BOOKING_WRITE_RATE_LIMIT_WINDOW_SECONDS,
        )
    ),
) -> BookingResponse:
    return await idempotent_execute(
        request=request,
        actor_id=current_user.id,
        callback=lambda: BookingService(db).create_booking(payload, current_user),
        serializer=lambda result: BookingResponse.model_validate(result),
    )


@router.get("/mine", response_model=list[PassengerBookingResponse])
def list_my_bookings(
    booking_status: BookingStatus | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[PassengerBookingResponse]:
    return BookingService(db).list_passenger_bookings(current_user, booking_status=booking_status, limit=limit, offset=offset)


@router.get("/managed", response_model=list[DriverBookingResponse])
def list_managed_bookings(
    booking_status: BookingStatus | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[DriverBookingResponse]:
    return BookingService(db).list_driver_bookings(current_user, booking_status=booking_status, limit=limit, offset=offset)


@router.get("/{booking_id}", response_model=BookingDetailResponse)
def get_booking_detail(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BookingDetailResponse:
    return BookingService(db).get_booking_detail(booking_id, current_user)


@router.post("/{booking_id}/boarding-code", response_model=BoardingOtpResponse)
def issue_boarding_code(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(
        rate_limit_dependency(
            "boarding-otp-issue",
            limit=lambda: settings.BOOKING_WRITE_RATE_LIMIT_MAX_REQUESTS,
            window_seconds=lambda: settings.BOOKING_WRITE_RATE_LIMIT_WINDOW_SECONDS,
        )
    ),
) -> BoardingOtpResponse:
    otp, expires_at = BookingService(db).issue_boarding_otp(booking_id, current_user)
    return BoardingOtpResponse(otp=otp, expires_at=expires_at)


@router.post("/{booking_id}/boarding/verify", response_model=BookingResponse)
def verify_boarding_code(
    booking_id: int,
    payload: BoardingOtpVerify,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(
        rate_limit_dependency(
            "boarding-otp-verify",
            limit=lambda: settings.BOOKING_WRITE_RATE_LIMIT_MAX_REQUESTS,
            window_seconds=lambda: settings.BOOKING_WRITE_RATE_LIMIT_WINDOW_SECONDS,
        )
    ),
) -> BookingResponse:
    return BookingService(db).verify_boarding_otp(booking_id, payload.otp, current_user)


@router.patch("/{booking_id}", response_model=BookingResponse)
async def update_booking_status(
    booking_id: int,
    payload: BookingStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(
        rate_limit_dependency(
            "booking-write",
            limit=lambda: settings.BOOKING_WRITE_RATE_LIMIT_MAX_REQUESTS,
            window_seconds=lambda: settings.BOOKING_WRITE_RATE_LIMIT_WINDOW_SECONDS,
        )
    ),
) -> BookingResponse:
    return await idempotent_execute(
        request=request,
        actor_id=current_user.id,
        callback=lambda: BookingService(db).update_status(booking_id, payload.status, current_user),
        serializer=lambda result: BookingResponse.model_validate(result),
    )
