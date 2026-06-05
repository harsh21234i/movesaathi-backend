import logging
from datetime import datetime, timezone
from datetime import timedelta

from fastapi import HTTPException, Request, status
from jose import JWTError
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from app.api.deps import revoke_token_from_payload
from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_email_verification_token,
    create_refresh_token,
    create_reset_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.auth import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ChangePasswordRequest,
    LoginRequest,
    RegisterResponse,
    RefreshRequest,
    RegisterRequest,
    SessionListResponse,
    SessionResponse,
    AccountSecurityResponse,
    ResendVerificationRequest,
    ResendVerificationResponse,
    ResetPasswordRequest,
    TokenResponse,
    VerifyEmailRequest,
)
from app.services.email import EmailService
from app.services.audit_log import AuditLogService
from app.services.maintenance_jobs import enqueue_audit_log_retention, enqueue_session_cleanup
from app.services.job_queue import Job, job_queue
from app.services.token_store import token_store


class AuthService:
    def __init__(self, db: Session) -> None:
        self.users = UserRepository(db)
        self.email_service = EmailService()
        self.audit_logs = AuditLogService(db)
        self.logger = logging.getLogger(__name__)
        self.retention_session_factory = sessionmaker(
            bind=db.get_bind(),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            future=True,
        )

    def register(self, payload: RegisterRequest) -> RegisterResponse:
        if self.users.get_by_email(payload.email):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already in use")

        try:
            user = User(
                full_name=payload.full_name,
                email=payload.email,
                phone_number=payload.phone_number,
                hashed_password=get_password_hash(payload.password),
                role=payload.role,
            )
            saved_user = self.users.create(user)
            self.users.db.commit()
            self.audit_logs.record(
                action="user_registered",
                actor_user_id=saved_user.id,
                entity_type="user",
                entity_id=str(saved_user.id),
                metadata={"role": saved_user.role.value, "email_verified": saved_user.email_verified},
            )
        except Exception:
            self.users.db.rollback()
            raise

        verification_token = self._issue_verification_token(saved_user)
        self._queue_verification_email(saved_user, verification_token)
        response = RegisterResponse.model_validate(saved_user)
        if not settings.is_production:
            response.verification_token = verification_token
        return response

    def login(self, payload: LoginRequest, *, request: Request | None = None) -> TokenResponse:
        user = self.users.get_by_email(payload.email)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        self._ensure_login_not_locked(user)

        if not verify_password(payload.password, user.hashed_password):
            self._record_failed_login(user)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        if settings.REQUIRE_EMAIL_VERIFICATION and not user.email_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email verification required before login",
            )

        self._clear_failed_logins(user)
        self.audit_logs.record(
            action="user_logged_in",
            actor_user_id=user.id,
            entity_type="session",
            metadata={"email": user.email},
        )
        return self._issue_token_pair(
            str(user.id),
            user_agent=self._request_user_agent(request),
            ip_address=self._request_ip_address(request),
        )

    def refresh(self, payload: RefreshRequest, *, request: Request | None = None) -> TokenResponse:
        token_payload = self._decode_expected_token(payload.refresh_token, expected_type="refresh")
        existing_session = token_store.get_session(token_payload["jti"])
        revoke_token_from_payload(token_payload)
        return self._issue_token_pair(
            str(token_payload["sub"]),
            user_agent=existing_session.user_agent if existing_session else self._request_user_agent(request),
            ip_address=existing_session.ip_address if existing_session else self._request_ip_address(request),
        )

    def logout(self, access_token: str, refresh_token: str | None = None) -> None:
        access_payload = self._decode_expected_token(access_token, expected_type="access")
        revoke_token_from_payload(access_payload)

        if refresh_token:
            refresh_payload = self._decode_expected_token(refresh_token, expected_type="refresh")
            revoke_token_from_payload(refresh_payload)
        self.audit_logs.record(
            action="user_logged_out",
            actor_user_id=int(access_payload["sub"]),
            entity_type="session",
            metadata={"refresh_revoked": bool(refresh_token)},
        )

    def forgot_password(self, payload: ForgotPasswordRequest) -> ForgotPasswordResponse:
        user = self.users.get_by_email(payload.email)
        if not user:
            return ForgotPasswordResponse(
                message="If an account exists for that email, a reset link has been generated.",
            )

        reset_token = create_reset_token(subject=str(user.id))
        self.email_service.queue_reset_password_email(
            to_email=user.email,
            full_name=user.full_name,
            reset_token=reset_token,
            enqueue=lambda handler: job_queue.enqueue(
                Job(
                    name=f"send-reset-password-email:{user.id}",
                    handler=handler,
                )
            ),
        )
        response = ForgotPasswordResponse(
            message="If an account exists for that email, a reset link has been generated.",
        )
        if not settings.is_production:
            response.reset_token = reset_token
        return response

    def resend_verification(self, payload: ResendVerificationRequest) -> ResendVerificationResponse:
        user = self.users.get_by_email(payload.email)
        response = ResendVerificationResponse(
            message="If an account exists for that email, a verification email has been sent.",
        )
        if not user or user.email_verified:
            return response

        verification_token = self._issue_verification_token(user)
        self._queue_verification_email(user, verification_token)
        if not settings.is_production:
            response.verification_token = verification_token
        return response

    def verify_email(self, payload: VerifyEmailRequest) -> None:
        verification_payload = self._decode_expected_token(payload.token, expected_type="verify-email")
        user = self.users.get_by_id(int(verification_payload["sub"]))
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        if user.email_verified:
            revoke_token_from_payload(verification_payload)
            return

        try:
            user.email_verified = True
            user.email_verified_at = datetime.now(timezone.utc)
            self.users.save(user)
            self.users.db.commit()
            self.audit_logs.record(
                action="email_verified",
                actor_user_id=user.id,
                entity_type="user",
                entity_id=str(user.id),
            )
            revoke_token_from_payload(verification_payload)
        except Exception:
            self.users.db.rollback()
            raise

    def reset_password(self, payload: ResetPasswordRequest) -> None:
        reset_payload = self._decode_expected_token(payload.token, expected_type="reset")
        user = self.users.get_by_id(int(reset_payload["sub"]))
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        try:
            user.hashed_password = get_password_hash(payload.new_password)
            self.users.save(user)
            self.users.db.commit()
            revoke_token_from_payload(reset_payload)
            token_store.revoke_user_sessions(user.id)
        except Exception:
            self.users.db.rollback()
            raise

    def change_password(self, payload: ChangePasswordRequest, current_user: User, access_token: str) -> None:
        if not verify_password(payload.current_password, current_user.hashed_password):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")

        try:
            current_user.hashed_password = get_password_hash(payload.new_password)
            self.users.save(current_user)
            self.users.db.commit()
            token_payload = self._decode_expected_token(access_token, expected_type="access")
            revoke_token_from_payload(token_payload)
            token_store.revoke_user_sessions(current_user.id)
            enqueue_session_cleanup(user_id=current_user.id)
            enqueue_audit_log_retention(session_factory=self.retention_session_factory, retention_days=90)
            self.audit_logs.record(
                action="password_changed",
                actor_user_id=current_user.id,
                entity_type="user",
                entity_id=str(current_user.id),
            )
        except Exception:
            self.users.db.rollback()
            raise

    def list_sessions(self, current_user: User, *, current_session_jti: str | None = None) -> SessionListResponse:
        sessions = token_store.list_sessions(current_user.id)
        return SessionListResponse(
            items=[
                SessionResponse(
                    jti=session.jti,
                    issued_at=session.issued_at.isoformat(),
                    expires_at=session.expires_at.isoformat(),
                    current_session=session.jti == current_session_jti if current_session_jti else False,
                    device_name=self._device_name(session.user_agent),
                    user_agent=session.user_agent,
                    ip_address=session.ip_address,
                )
                for session in sessions
            ]
        )

    def revoke_session(self, current_user: User, session_jti: str) -> None:
        sessions = token_store.list_sessions(current_user.id)
        if not any(session.jti == session_jti for session in sessions):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        token_store.revoke_session(session_jti)

    def account_security(self, current_user: User) -> AccountSecurityResponse:
        locked_until = self._normalize_datetime(current_user.locked_until)
        is_locked = bool(locked_until and locked_until > datetime.now(timezone.utc))
        reason = "Account temporarily locked due to too many failed login attempts" if is_locked else None
        return AccountSecurityResponse(
            failed_login_attempts=current_user.failed_login_attempts,
            locked_until=locked_until,
            is_locked=is_locked,
            lockout_reason=reason,
        )

    def _issue_token_pair(self, subject: str, *, user_agent: str | None = None, ip_address: str | None = None) -> TokenResponse:
        refresh_token = create_refresh_token(subject=subject)
        refresh_payload = decode_token(refresh_token)
        access_token = create_access_token(subject=subject, extra_claims={"session_jti": refresh_payload["jti"]})
        token_store.register_session(
            user_id=int(subject),
            jti=refresh_payload["jti"],
            issued_at=datetime.now(timezone.utc),
            expires_at=datetime.fromtimestamp(refresh_payload["exp"], tz=timezone.utc),
            user_agent=user_agent,
            ip_address=ip_address,
        )
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)

    def _ensure_login_not_locked(self, user: User) -> None:
        locked_until = self._normalize_datetime(user.locked_until)
        if locked_until and locked_until > datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail="Account temporarily locked due to too many failed login attempts",
            )

    def _record_failed_login(self, user: User) -> None:
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.AUTH_MAX_FAILED_LOGIN_ATTEMPTS:
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=settings.AUTH_LOCKOUT_WINDOW_MINUTES)
            user.failed_login_attempts = 0
        self.users.save(user)
        self.users.db.commit()

    def _clear_failed_logins(self, user: User) -> None:
        if user.failed_login_attempts or user.locked_until:
            user.failed_login_attempts = 0
            user.locked_until = None
            self.users.save(user)
            self.users.db.commit()

    def _normalize_datetime(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _issue_verification_token(self, user: User) -> str:
        return create_email_verification_token(subject=str(user.id))

    def _request_user_agent(self, request: Request | None) -> str | None:
        if not request:
            return None
        user_agent = request.headers.get("user-agent")
        return user_agent or None

    def _request_ip_address(self, request: Request | None) -> str | None:
        if not request or not request.client:
            return None
        return request.client.host

    def _device_name(self, user_agent: str | None) -> str:
        if not user_agent:
            return "Unknown device"
        lowered = user_agent.lower()
        if "mobile" in lowered or "android" in lowered or "iphone" in lowered:
            return "Mobile browser"
        if "windows" in lowered:
            return "Windows browser"
        if "mac os" in lowered or "macintosh" in lowered:
            return "Mac browser"
        if "linux" in lowered:
            return "Linux browser"
        return "Browser"

    def _queue_verification_email(self, user: User, verification_token: str) -> None:
        def send_verification() -> None:
            try:
                self.email_service.send_verification_email(
                    to_email=user.email,
                    full_name=user.full_name,
                    verification_token=verification_token,
                )
            except Exception:
                self.logger.exception("Failed to send verification email to user_id=%s", user.id)

        job_queue.enqueue(
            Job(
                name=f"send-verification-email:{user.id}",
                handler=send_verification,
            )
        )

    def _decode_expected_token(self, token: str, *, expected_type: str) -> dict:
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
        try:
            payload = decode_token(token)
        except JWTError:
            raise credentials_exception from None

        if payload.get("type") != expected_type:
            raise credentials_exception
        if token_store.is_revoked(payload.get("jti", "")):
            raise credentials_exception
        if datetime.fromtimestamp(payload["exp"], tz=timezone.utc) <= datetime.now(timezone.utc):
            raise credentials_exception
        return payload
