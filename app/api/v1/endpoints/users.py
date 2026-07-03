from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.user import DriverVerificationResponse, DriverVerificationUpdate, UserResponse, UserUpdate
from app.services.user import UserService

router = APIRouter()


@router.get("/me", response_model=UserResponse)
def get_profile(current_user: User = Depends(get_current_user)) -> UserResponse:
    return current_user


@router.patch("/me", response_model=UserResponse)
def update_profile(
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    return UserService(db).update_user(current_user, payload)


@router.get("/me/driver-profile", response_model=DriverVerificationResponse)
def get_driver_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DriverVerificationResponse:
    return UserService(db).get_driver_verification_profile(current_user)


@router.patch("/me/driver-profile", response_model=DriverVerificationResponse)
def update_driver_profile(
    payload: DriverVerificationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DriverVerificationResponse:
    return UserService(db).update_driver_verification_profile(current_user, payload)
