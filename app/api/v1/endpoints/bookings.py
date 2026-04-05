from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.booking import BookingCreate, BookingResponse, BookingStatusUpdate
from app.services.booking import BookingService

router = APIRouter()


@router.post("", response_model=BookingResponse)
def create_booking(
    payload: BookingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BookingResponse:
    return BookingService(db).create_booking(payload, current_user)


@router.patch("/{booking_id}", response_model=BookingResponse)
def update_booking_status(
    booking_id: int,
    payload: BookingStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BookingResponse:
    return BookingService(db).update_status(booking_id, payload.status, current_user)
