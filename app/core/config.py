from functools import lru_cache
from typing import Literal

from pydantic import ValidationInfo, field_validator, model_validator
from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    PROJECT_NAME: str = "MooveSaathi"
    APP_ENV: Literal["development", "test", "production"] = "development"
    DEBUG: bool = False
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = Field(default="change-this-super-secret-key-12345", min_length=32)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    RESET_TOKEN_EXPIRE_MINUTES: int = 30
    EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES: int = 1440
    REQUIRE_EMAIL_VERIFICATION: bool = False
    LOGIN_RATE_LIMIT_MAX_REQUESTS: int = 5
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 60
    FORGOT_PASSWORD_RATE_LIMIT_MAX_REQUESTS: int = 3
    FORGOT_PASSWORD_RATE_LIMIT_WINDOW_SECONDS: int = 900
    RESET_PASSWORD_RATE_LIMIT_MAX_REQUESTS: int = 5
    RESET_PASSWORD_RATE_LIMIT_WINDOW_SECONDS: int = 900
    RESEND_VERIFICATION_RATE_LIMIT_MAX_REQUESTS: int = 3
    RESEND_VERIFICATION_RATE_LIMIT_WINDOW_SECONDS: int = 900
    CHAT_MESSAGE_RATE_LIMIT_MAX_REQUESTS: int = 20
    CHAT_MESSAGE_RATE_LIMIT_WINDOW_SECONDS: int = 60
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@db:5432/moovesaathi"
    REDIS_URL: str = "redis://redis:6379/0"
    REDIS_SOCKET_CONNECT_TIMEOUT: float = 0.5
    REDIS_SOCKET_TIMEOUT: float = 0.5
    EMAILS_ENABLED: bool = False
    EMAIL_FROM: str = "no-reply@moovesaathi.local"
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_USE_TLS: bool = True
    SMTP_USE_SSL: bool = False
    FRONTEND_URL: str = "http://localhost:5173"
    AUTO_CREATE_TABLES: bool = True
    SQL_ECHO: bool = False
    BACKEND_CORS_ORIGINS: list[AnyHttpUrl | str] = ["http://localhost:5173"]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def should_create_tables(self) -> bool:
        return self.AUTO_CREATE_TABLES and not self.is_production

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, value: str, info: ValidationInfo) -> str:
        app_env = info.data.get("APP_ENV", "development")
        insecure_defaults = {
            "change-this-super-secret-key-12345",
            "replace-with-a-strong-32-plus-character-secret",
        }
        if app_env == "production" and value in insecure_defaults:
            raise ValueError("SECRET_KEY must be overridden in production")
        return value

    @model_validator(mode="after")
    def validate_runtime_settings(self) -> "Settings":
        if self.is_production and "localhost" in self.BACKEND_CORS_ORIGINS:
            raise ValueError("BACKEND_CORS_ORIGINS must be explicitly configured for production")
        if self.EMAILS_ENABLED and not self.SMTP_HOST:
            raise ValueError("SMTP_HOST must be configured when EMAILS_ENABLED is true")
        if self.EMAILS_ENABLED and self.SMTP_USE_TLS and self.SMTP_USE_SSL:
            raise ValueError("SMTP_USE_TLS and SMTP_USE_SSL cannot both be enabled")
        return self


@lru_cache
def get_settings() -> "Settings":
    return Settings()


settings = get_settings()
