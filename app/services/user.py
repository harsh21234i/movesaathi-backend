from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.user import UserUpdate


class UserService:
    def __init__(self, db: Session) -> None:
        self.users = UserRepository(db)

    def update_user(self, current_user: User, payload: UserUpdate) -> User:
        updates = payload.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(current_user, field, value)
        return self.users.save(current_user)
