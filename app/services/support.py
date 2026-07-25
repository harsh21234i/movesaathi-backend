from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import HTTPException, Request, status
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.notification import NotificationType
from app.models.user import DriverVerificationStatus, User, UserRole
from app.repositories.user import UserRepository
from app.schemas.support import DriverVerificationHistoryResponse, DriverVerificationReviewRequest, SupportUserResponse
from app.services.audit_log import AuditLogService
from app.services.notification_jobs import enqueue_notification


class SupportService:
    def __init__(self, db: Session) -> None:
        self.users = UserRepository(db)
        self.audit_logs = AuditLogService(db)
        self.redis = Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
        )
        self.logger = logging.getLogger(__name__)
        self.notification_session_factory = sessionmaker(
            bind=db.get_bind(),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            future=True,
        )

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
        return self._user_response(user)

    def search_users(self, *, email: str | None, request: Request) -> list[SupportUserResponse]:
        self._require_support_auth(request)
        items = self.users.search(email=email)
        return [self._user_response(user) for user in items]

    def list_pending_driver_verifications(
        self,
        *,
        request: Request,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SupportUserResponse]:
        self._require_support_auth(request)
        items = self.users.list_pending_driver_verifications(limit=limit, offset=offset)
        return [self._user_response(user) for user in items]

    def list_driver_verifications(
        self,
        *,
        request: Request,
        verification_status: DriverVerificationStatus | None = None,
        email: str | None = None,
        vehicle_plate_number: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SupportUserResponse]:
        self._require_support_auth(request)
        items = self.users.list_driver_verifications(
            verification_status=verification_status,
            email=email,
            vehicle_plate_number=vehicle_plate_number,
            limit=limit,
            offset=offset,
        )
        return [self._user_response(user) for user in items]

    def review_driver_verification(
        self,
        *,
        user_id: int,
        payload: DriverVerificationReviewRequest,
        request: Request,
    ) -> SupportUserResponse:
        self._require_support_auth(request)
        if payload.status not in {DriverVerificationStatus.verified, DriverVerificationStatus.rejected}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Driver verification can only be approved or rejected",
            )
        if payload.status == DriverVerificationStatus.rejected and not payload.rejection_reason:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Rejection reason is required")

        user = self.users.get_by_id(user_id)
        if not user or user.role != UserRole.driver:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Driver not found")

        try:
            user.driver_verification_status = payload.status
            user.driver_verification_rejection_reason = (
                payload.rejection_reason if payload.status == DriverVerificationStatus.rejected else None
            )
            user.driver_profile_reviewed_at = datetime.now(timezone.utc)
            saved_user = self.users.save(user)
            self.audit_logs.record(
                action=f"driver_verification_{payload.status.value}",
                actor_user_id=None,
                entity_type="user",
                entity_id=str(saved_user.id),
                metadata={
                    "driver_id": saved_user.id,
                    "status": payload.status.value,
                    "rejection_reason": saved_user.driver_verification_rejection_reason,
                },
                request=request,
                commit=False,
            )
            self.users.db.commit()
        except Exception:
            self.users.db.rollback()
            raise

        self._enqueue_driver_verification_notification(saved_user)
        self._publish_driver_verification_event(saved_user)
        return self._user_response(saved_user)

    def _user_response(self, user: User) -> SupportUserResponse:
        summary = self.audit_logs.summarize_my_audit_logs(user)
        verification_history = DriverVerificationHistoryResponse(
            items=self.audit_logs.list_entity_audit_logs(
                entity_type="user",
                entity_id=str(user.id),
                action_prefix="driver_verification_",
                limit=10,
            )
        )
        return SupportUserResponse.model_validate(
            {
                **user.__dict__,
                "audit_summary": summary,
                "driver_verification_history": verification_history,
            }
        )

    def _enqueue_driver_verification_notification(self, user: User) -> None:
        approved = user.driver_verification_status == DriverVerificationStatus.verified
        enqueue_notification(
            session_factory=self.notification_session_factory,
            recipient_id=user.id,
            notification_type=(
                NotificationType.driver_verification_approved
                if approved
                else NotificationType.driver_verification_rejected
            ),
            title="Driver verification approved" if approved else "Driver verification rejected",
            body=(
                "Your driver profile is verified. You can now go online and accept ride requests."
                if approved
                else user.driver_verification_rejection_reason or "Your driver profile needs updates before approval."
            ),
        )

    def _publish_driver_verification_event(self, user: User) -> None:
        payload = {
            "event_type": "driver_verification_status_changed",
            "driver_verification_status": user.driver_verification_status.value,
            "driver_verification_rejection_reason": user.driver_verification_rejection_reason,
            "driver_profile_reviewed_at": user.driver_profile_reviewed_at.isoformat()
            if user.driver_profile_reviewed_at
            else None,
        }
        try:
            self.redis.publish(f"dispatch:driver:{user.id}", json.dumps(payload))
        except RedisError:
            self.logger.exception("Failed to publish driver verification event for user_id=%s", user.id)
        except Exception:
            self.logger.exception("Unexpected driver verification publish failure for user_id=%s", user.id)
