from __future__ import annotations

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.support import SupportUserResponse
from app.services.audit_log import AuditLogService


class SupportService:
    def __init__(self, db: Session) -> None:
        self.users = UserRepository(db)
        self.audit_logs = AuditLogService(db)

    def _require_support_auth(self, request: Request) -> None:
        if not settings.SUPPORT_API_ENABLED:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        token = request.headers.get("x-support-token")
        if not token or token != settings.SUPPORT_API_KEY:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid support token")

    def get_user(self, user_id: int, request: Request) -> SupportUserResponse:
        self._require_support_auth(request)
        user = self.users.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        summary = self.audit_logs.summarize_my_audit_logs(user)
        return SupportUserResponse.model_validate({**user.__dict__, "audit_summary": summary})

    def search_users(self, *, email: str | None, request: Request) -> list[SupportUserResponse]:
        self._require_support_auth(request)
        items = self.users.search(email=email)
        return [SupportUserResponse.model_validate({**user.__dict__, "audit_summary": self.audit_logs.summarize_my_audit_logs(user)}) for user in items]
