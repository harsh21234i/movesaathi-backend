from functools import lru_cache

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    PROJECT_NAME: str = "MooveSaathi"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = Field(default="change-this-super-secret-key-12345", min_length=32)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@db:5432/moovesaathi"
    REDIS_URL: str = "redis://redis:6379/0"
    BACKEND_CORS_ORIGINS: list[AnyHttpUrl | str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> "Settings":
    return Settings()


settings = get_settings()
