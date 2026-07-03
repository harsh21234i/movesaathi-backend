from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.support import (
    DriverVerificationReviewRequest,
    PendingDriverVerificationResponse,
    SupportUserResponse,
    SupportUserSearchResponse,
)
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
