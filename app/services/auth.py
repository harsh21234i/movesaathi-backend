import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy.orm import Session

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
    LoginRequest,
    RegisterResponse,
    RefreshRequest,
    RegisterRequest,
    ResendVerificationRequest,
    ResendVerificationResponse,
    ResetPasswordRequest,
    TokenResponse,
    VerifyEmailRequest,
)
from app.services.email import EmailService
from app.services.token_store import token_store


class AuthService:
    def __init__(self, db: Session) -> None:
        self.users = UserRepository(db)
        self.email_service = EmailService()
        self.logger = logging.getLogger(__name__)

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
        except Exception:
            self.users.db.rollback()
            raise

        verification_token = self._issue_verification_token(saved_user)
        self._send_verification_email(saved_user, verification_token)
        response = RegisterResponse.model_validate(saved_user)
        if not settings.is_production:
            response.verification_token = verification_token
        return response

    def login(self, payload: LoginRequest) -> TokenResponse:
        user = self.users.get_by_email(payload.email)
        if not user or not verify_password(payload.password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        if settings.REQUIRE_EMAIL_VERIFICATION and not user.email_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email verification required before login",
            )

        return self._issue_token_pair(str(user.id))

    def refresh(self, payload: RefreshRequest) -> TokenResponse:
        token_payload = self._decode_expected_token(payload.refresh_token, expected_type="refresh")
        revoke_token_from_payload(token_payload)
        return self._issue_token_pair(str(token_payload["sub"]))

    def logout(self, access_token: str, refresh_token: str | None = None) -> None:
        access_payload = self._decode_expected_token(access_token, expected_type="access")
        revoke_token_from_payload(access_payload)

        if refresh_token:
            refresh_payload = self._decode_expected_token(refresh_token, expected_type="refresh")
            revoke_token_from_payload(refresh_payload)

    def forgot_password(self, payload: ForgotPasswordRequest) -> ForgotPasswordResponse:
        user = self.users.get_by_email(payload.email)
        if not user:
            return ForgotPasswordResponse(
                message="If an account exists for that email, a reset link has been generated.",
            )

        reset_token = create_reset_token(subject=str(user.id))
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
        self._send_verification_email(user, verification_token)
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
        except Exception:
            self.users.db.rollback()
            raise

    def _issue_token_pair(self, subject: str) -> TokenResponse:
        access_token = create_access_token(subject=subject)
        refresh_token = create_refresh_token(subject=subject)
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)

    def _issue_verification_token(self, user: User) -> str:
        return create_email_verification_token(subject=str(user.id))

    def _send_verification_email(self, user: User, verification_token: str) -> None:
        try:
            self.email_service.send_verification_email(
                to_email=user.email,
                full_name=user.full_name,
                verification_token=verification_token,
            )
        except Exception:
            self.logger.exception("Failed to send verification email to user_id=%s", user.id)

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
