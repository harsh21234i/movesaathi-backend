from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.support import SupportUserResponse, SupportUserSearchResponse
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
