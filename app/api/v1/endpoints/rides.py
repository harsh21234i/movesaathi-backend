from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.ride import RideCreate, RideResponse, RideSearchParams
from app.services.ride import RideService

router = APIRouter()


@router.post("", response_model=RideResponse, status_code=status.HTTP_201_CREATED)
def create_ride(
    payload: RideCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RideResponse:
    return RideService(db).create_ride(payload, current_user)


@router.get("/mine", response_model=list[RideResponse])
def list_my_rides(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[RideResponse]:
    return RideService(db).list_driver_rides(current_user)


@router.get("", response_model=list[RideResponse])
def search_rides(
    origin: str | None = Query(default=None),
    destination: str | None = Query(default=None),
    departure_after: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[RideResponse]:
    params = RideSearchParams(origin=origin, destination=destination, departure_after=departure_after)
    return RideService(db).search_rides(params)
