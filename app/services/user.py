from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.user import DriverVerificationStatus, User, UserRole
from app.repositories.user import UserRepository
from app.schemas.user import DriverVerificationResponse, DriverVerificationUpdate, UserUpdate
from app.services.audit_log import AuditLogService


class UserService:
    def __init__(self, db: Session) -> None:
        self.users = UserRepository(db)
        self.audit_logs = AuditLogService(db)

    def update_user(self, current_user: User, payload: UserUpdate) -> User:
        updates = payload.model_dump(exclude_unset=True)
        try:
            for field, value in updates.items():
                setattr(current_user, field, value)
            saved_user = self.users.save(current_user)
            self.users.db.commit()
            return saved_user
        except Exception:
            self.users.db.rollback()
            raise

    def get_driver_verification_profile(self, current_user: User) -> DriverVerificationResponse:
        self._ensure_driver(current_user)
        return DriverVerificationResponse.model_validate(current_user)

    def update_driver_verification_profile(
        self,
        current_user: User,
        payload: DriverVerificationUpdate,
    ) -> DriverVerificationResponse:
        self._ensure_driver(current_user)
        updates = payload.model_dump(exclude_unset=True)
        try:
            for field, value in updates.items():
                setattr(current_user, field, value)
            current_user.driver_verification_status = DriverVerificationStatus.pending
            current_user.driver_verification_rejection_reason = None
            current_user.driver_profile_submitted_at = datetime.now(timezone.utc)
            current_user.driver_profile_reviewed_at = None
            saved_user = self.users.save(current_user)
            self.audit_logs.record(
                action="driver_verification_profile_updated",
                actor_user_id=current_user.id,
                entity_type="user",
                entity_id=str(current_user.id),
                metadata={
                    "vehicle_make": saved_user.vehicle_make,
                    "vehicle_model": saved_user.vehicle_model,
                    "vehicle_plate_number": saved_user.vehicle_plate_number,
                },
                commit=False,
            )
            self.users.db.commit()
            return DriverVerificationResponse.model_validate(saved_user)
        except Exception:
            self.users.db.rollback()
            raise

    def _ensure_driver(self, current_user: User) -> None:
        if current_user.role != UserRole.driver:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Driver profile is only available for drivers")
