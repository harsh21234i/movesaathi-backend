from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.core.rate_limit import rate_limit_dependency
from app.models.user import User
from app.schemas.review import ReviewCreate, ReviewResponse
from app.services.review import ReviewService

router = APIRouter()


@router.post("", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
def create_review(
    payload: ReviewCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(
        rate_limit_dependency(
            "review-create",
            limit=lambda: settings.REVIEW_CREATE_RATE_LIMIT_MAX_REQUESTS,
            window_seconds=lambda: settings.REVIEW_CREATE_RATE_LIMIT_WINDOW_SECONDS,
        )
    ),
) -> ReviewResponse:
    return ReviewService(db).create_review(payload, current_user)
