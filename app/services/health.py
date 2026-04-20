from collections.abc import Callable

from redis import Redis
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.session import SessionLocal


def check_database() -> tuple[bool, str]:
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
        return True, "ok"
    except SQLAlchemyError as exc:
        return False, str(exc)


def check_redis() -> tuple[bool, str]:
    client = Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
        socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
    )
    try:
        client.ping()
        return True, "ok"
    except Exception as exc:
        return False, str(exc)
    finally:
        try:
            client.close()
        except Exception:
            pass


def build_readiness_payload(
    *,
    db_check: Callable[[], tuple[bool, str]] = check_database,
    redis_check: Callable[[], tuple[bool, str]] = check_redis,
) -> tuple[dict[str, object], bool]:
    database_ok, database_detail = db_check()
    redis_ok, redis_detail = redis_check()
    healthy = database_ok and redis_ok

    payload = {
        "status": "ok" if healthy else "degraded",
        "service": settings.PROJECT_NAME,
        "environment": settings.APP_ENV,
        "checks": {
            "database": {
                "status": "ok" if database_ok else "error",
                "detail": database_detail,
            },
            "redis": {
                "status": "ok" if redis_ok else "error",
                "detail": redis_detail,
            },
        },
    }
    return payload, healthy
