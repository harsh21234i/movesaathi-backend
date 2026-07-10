from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import DriverVerificationStatus, User, UserRole


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, user_id: int) -> User | None:
        return self.db.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        return self.db.scalar(stmt)

    def search(self, *, email: str | None = None) -> list[User]:
        stmt = select(User)
        if email:
            stmt = stmt.where(User.email.ilike(f"%{email}%"))
        stmt = stmt.order_by(User.id.asc()).limit(50)
        return list(self.db.scalars(stmt))

    def list_pending_driver_verifications(self, *, limit: int = 50, offset: int = 0) -> list[User]:
        return self.list_driver_verifications(
            verification_status=DriverVerificationStatus.pending,
            limit=limit,
            offset=offset,
        )

    def list_driver_verifications(
        self,
        *,
        verification_status: DriverVerificationStatus | None = None,
        email: str | None = None,
        vehicle_plate_number: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[User]:
        stmt = select(User).where(User.role == UserRole.driver)
        if verification_status:
            stmt = stmt.where(User.driver_verification_status == verification_status)
        if email:
            stmt = stmt.where(User.email.ilike(f"%{email}%"))
        if vehicle_plate_number:
            stmt = stmt.where(User.vehicle_plate_number.ilike(f"%{vehicle_plate_number}%"))
        stmt = (
            stmt.order_by(User.driver_profile_submitted_at.asc().nullsfirst(), User.created_at.asc())
            .offset(offset)
            .limit(limit)
        )
        return list(self.db.scalars(stmt))

    def create(self, user: User) -> User:
        self.db.add(user)
        self.db.flush()
        self.db.refresh(user)
        return user

    def save(self, user: User) -> User:
        self.db.add(user)
        self.db.flush()
        self.db.refresh(user)
        return user
