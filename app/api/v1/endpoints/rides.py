from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.api.idempotency import idempotent_execute
from app.core.config import settings
from app.core.rate_limit import rate_limit_dependency
from app.models.ride import RideStatus
from app.models.user import User
from app.schemas.ride import (
    RideCreate,
    RideLocationAccessResponse,
    RideDetailResponse,
    RideLocationCreate,
    RideLocationResponse,
    RideResponse,
    RideSearchParams,
    RideUpdate,
)
from app.services.ride import RideService

router = APIRouter()


@router.post("", response_model=RideResponse, status_code=status.HTTP_201_CREATED)
async def create_ride(
    payload: RideCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(
        rate_limit_dependency(
            "ride-write",
            limit=lambda: settings.RIDE_WRITE_RATE_LIMIT_MAX_REQUESTS,
            window_seconds=lambda: settings.RIDE_WRITE_RATE_LIMIT_WINDOW_SECONDS,
        )
    ),
) -> Response:
    return await idempotent_execute(
        request=request,
        actor_id=current_user.id,
        callback=lambda: RideService(db).create_ride(payload, current_user),
        serializer=lambda result: RideResponse.model_validate(result),
        status_code=status.HTTP_201_CREATED,
    )


@router.get("/mine", response_model=list[RideResponse])
def list_my_rides(
    ride_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[RideResponse]:
    normalized_status = RideStatus(ride_status) if ride_status else None
    return RideService(db).list_driver_rides(current_user, ride_status=normalized_status, limit=limit, offset=offset)


@router.get("/{ride_id}", response_model=RideDetailResponse)
def get_ride_detail(
    ride_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RideDetailResponse:
    return RideService(db).get_ride_detail(ride_id, current_user)


@router.patch("/{ride_id}", response_model=RideResponse)
async def update_ride(
    ride_id: int,
    payload: RideUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(
        rate_limit_dependency(
            "ride-write",
            limit=lambda: settings.RIDE_WRITE_RATE_LIMIT_MAX_REQUESTS,
            window_seconds=lambda: settings.RIDE_WRITE_RATE_LIMIT_WINDOW_SECONDS,
        )
    ),
) -> Response:
    return await idempotent_execute(
        request=request,
        actor_id=current_user.id,
        callback=lambda: RideService(db).update_ride(ride_id, payload, current_user),
        serializer=lambda result: RideResponse.model_validate(result),
    )


@router.delete("/{ride_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_ride(
    ride_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(
        rate_limit_dependency(
            "ride-write",
            limit=lambda: settings.RIDE_WRITE_RATE_LIMIT_MAX_REQUESTS,
            window_seconds=lambda: settings.RIDE_WRITE_RATE_LIMIT_WINDOW_SECONDS,
        )
    ),
) -> Response:
    cached = await idempotent_execute(
        request=request,
        actor_id=current_user.id,
        callback=lambda: RideService(db).cancel_ride(ride_id, current_user),
        serializer=lambda _: None,
        status_code=status.HTTP_204_NO_CONTENT,
    )
    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
        headers=dict(cached.headers),
    )


@router.post("/{ride_id}/complete", response_model=RideResponse)
async def complete_ride(
    ride_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(
        rate_limit_dependency(
            "ride-write",
            limit=lambda: settings.RIDE_WRITE_RATE_LIMIT_MAX_REQUESTS,
            window_seconds=lambda: settings.RIDE_WRITE_RATE_LIMIT_WINDOW_SECONDS,
        )
    ),
) -> Response:
    return await idempotent_execute(
        request=request,
        actor_id=current_user.id,
        callback=lambda: RideService(db).complete_ride(ride_id, current_user),
        serializer=lambda result: RideResponse.model_validate(result),
    )


@router.post("/{ride_id}/location", response_model=RideLocationResponse)
def update_ride_location(
    ride_id: int,
    payload: RideLocationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(
        rate_limit_dependency(
            "location-update",
            limit=lambda: settings.LOCATION_UPDATE_RATE_LIMIT_MAX_REQUESTS,
            window_seconds=lambda: settings.LOCATION_UPDATE_RATE_LIMIT_WINDOW_SECONDS,
        )
    ),
) -> RideLocationResponse:
    return RideService(db).update_location(ride_id, payload, current_user)


@router.get("/{ride_id}/location/latest", response_model=RideLocationResponse)
def get_latest_ride_location(
    ride_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RideLocationResponse:
    return RideService(db).get_latest_location(ride_id, current_user)


@router.get("/{ride_id}/location/history", response_model=list[RideLocationResponse])
def list_ride_location_history(
    ride_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[RideLocationResponse]:
    return RideService(db).list_location_history(ride_id, current_user, limit=limit)


@router.get("/{ride_id}/location/access", response_model=RideLocationAccessResponse)
def get_ride_location_access(
    ride_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RideLocationAccessResponse:
    return RideService(db).get_location_access(ride_id, current_user)


@router.get("", response_model=list[RideResponse])
def search_rides(
    origin: str | None = Query(default=None),
    destination: str | None = Query(default=None),
    departure_after: datetime | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[RideResponse]:
    params = RideSearchParams(
        origin=origin,
        destination=destination,
        departure_after=departure_after,
        limit=limit,
        offset=offset,
    )
    return RideService(db).search_rides(params)
