from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.user import UserUpdate


class UserService:
    def __init__(self, db: Session) -> None:
        self.users = UserRepository(db)

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
