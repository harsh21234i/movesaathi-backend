from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps import oauth2_scheme
from app.core.config import settings
from app.core.rate_limit import rate_limit_dependency
from app.schemas.auth import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LogoutRequest,
    RegisterResponse,
    RefreshRequest,
    RegisterRequest,
    ResendVerificationRequest,
    ResendVerificationResponse,
    ResetPasswordRequest,
    TokenResponse,
    VerifyEmailRequest,
)
from app.services.auth import AuthService

router = APIRouter()


def _request_email_identifier(request: Request) -> str:
    body = getattr(request.state, "json_body", None) or {}
    email = body.get("email")
    client_host = request.client.host if request.client else "unknown"
    return f"{client_host}:{email or 'unknown'}"


async def cache_json_body(request: Request) -> None:
    request.state.json_body = await request.json()


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> RegisterResponse:
    return AuthService(db).register(payload)


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    db: Session = Depends(get_db),
    _: None = Depends(cache_json_body),
    __: None = Depends(
        rate_limit_dependency(
            "auth-login",
            limit=lambda: settings.LOGIN_RATE_LIMIT_MAX_REQUESTS,
            window_seconds=lambda: settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
            identifier_getter=_request_email_identifier,
        )
    ),
) -> TokenResponse:
    return AuthService(db).login(payload)


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_db),
    _: None = Depends(cache_json_body),
    __: None = Depends(
        rate_limit_dependency(
            "auth-forgot-password",
            limit=lambda: settings.FORGOT_PASSWORD_RATE_LIMIT_MAX_REQUESTS,
            window_seconds=lambda: settings.FORGOT_PASSWORD_RATE_LIMIT_WINDOW_SECONDS,
            identifier_getter=_request_email_identifier,
        )
    ),
) -> ForgotPasswordResponse:
    return AuthService(db).forgot_password(payload)


@router.post("/resend-verification", response_model=ResendVerificationResponse)
def resend_verification(
    payload: ResendVerificationRequest,
    db: Session = Depends(get_db),
    _: None = Depends(cache_json_body),
    __: None = Depends(
        rate_limit_dependency(
            "auth-resend-verification",
            limit=lambda: settings.RESEND_VERIFICATION_RATE_LIMIT_MAX_REQUESTS,
            window_seconds=lambda: settings.RESEND_VERIFICATION_RATE_LIMIT_WINDOW_SECONDS,
            identifier_getter=_request_email_identifier,
        )
    ),
) -> ResendVerificationResponse:
    return AuthService(db).resend_verification(payload)


@router.post("/verify-email", status_code=status.HTTP_204_NO_CONTENT)
def verify_email(payload: VerifyEmailRequest, db: Session = Depends(get_db)) -> Response:
    AuthService(db).verify_email(payload)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
    _: None = Depends(
        rate_limit_dependency(
            "auth-reset-password",
            limit=lambda: settings.RESET_PASSWORD_RATE_LIMIT_MAX_REQUESTS,
            window_seconds=lambda: settings.RESET_PASSWORD_RATE_LIMIT_WINDOW_SECONDS,
        )
    ),
) -> Response:
    AuthService(db).reset_password(payload)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/refresh", response_model=TokenResponse)
def refresh_tokens(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return AuthService(db).refresh(payload)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    payload: LogoutRequest,
    db: Session = Depends(get_db),
    access_token: str = Depends(oauth2_scheme),
) -> Response:
    AuthService(db).logout(access_token=access_token, refresh_token=payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
