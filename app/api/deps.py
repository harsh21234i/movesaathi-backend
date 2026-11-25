from collections.abc import Generator
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.config import settings
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


def get_user_from_access_token(db: Session, token: str) -> User:
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        if payload.get("type") != "access" or token_store.is_revoked(payload.get("jti", "")):
            raise invalid
        session_jti = payload.get("session_jti")
        if session_jti and token_store.is_revoked(session_jti):
            raise invalid
        user_id = int(payload.get("sub", "0"))
    except (JWTError, ValueError):
        raise invalid from None
    user = UserRepository(db).get_by_id(user_id)
    if not user:
        raise invalid
    return user


def get_current_user(
    db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)
) -> User:
    return get_user_from_access_token(db, token)


def require_support_auth(request: Request) -> None:
    if not settings.SUPPORT_API_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    token = request.headers.get("x-support-token")
    if not token or token != settings.SUPPORT_API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid support token")


def revoke_token_from_payload(payload: dict) -> None:
    jti = payload.get("jti")
    exp = payload.get("exp")
    if not jti or exp is None:
        return
    token_store.revoke(jti, datetime.fromtimestamp(exp, tz=timezone.utc))
