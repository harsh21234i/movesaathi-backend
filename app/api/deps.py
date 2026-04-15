from collections.abc import Generator
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import SessionLocal
from app.models.user import User
from app.repositories.user import UserRepository
from app.services.token_store import token_store

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise credentials_exception
        if token_store.is_revoked(payload.get("jti", "")):
            raise credentials_exception
        user_id = int(payload.get("sub", "0"))
    except (JWTError, ValueError):
        raise credentials_exception from None

    user = UserRepository(db).get_by_id(user_id)
    if not user:
        raise credentials_exception
    return user


def revoke_token_from_payload(payload: dict) -> None:
    jti = payload.get("jti")
    exp = payload.get("exp")
    if not jti or exp is None:
        return
    token_store.revoke(jti, datetime.fromtimestamp(exp, tz=timezone.utc))
