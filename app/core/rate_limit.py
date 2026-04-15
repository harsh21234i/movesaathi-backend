from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from time import time

from fastapi import HTTPException, Request, status
from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings


@dataclass
class LimitRecord:
    count: int
    expires_at: float


class RateLimiter:
    def __init__(self) -> None:
        self._redis = Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
        )
        self._memory: dict[str, LimitRecord] = {}
        self._lock = Lock()

    def enforce(self, key: str, *, limit: int, window_seconds: int) -> None:
        current = self._increment(key, window_seconds)
        if current > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
            )

    def reset(self) -> None:
        with self._lock:
            self._memory.clear()

    def _increment(self, key: str, window_seconds: int) -> int:
        redis_key = f"rate-limit:{key}"
        try:
            count = self._redis.incr(redis_key)
            if count == 1:
                self._redis.expire(redis_key, window_seconds)
            return int(count)
        except RedisError:
            pass

        now = time()
        with self._lock:
            record = self._memory.get(redis_key)
            if record is None or record.expires_at <= now:
                record = LimitRecord(count=0, expires_at=now + window_seconds)
            record.count += 1
            self._memory[redis_key] = record
            self._prune(now)
            return record.count

    def _prune(self, now: float) -> None:
        self._memory = {
            key: record for key, record in self._memory.items() if record.expires_at > now
        }


rate_limiter = RateLimiter()


def rate_limit_dependency(
    scope: str,
    *,
    limit: int | Callable[[], int],
    window_seconds: int | Callable[[], int],
    identifier_getter: Callable[[Request], str] | None = None,
) -> Callable[[Request], None]:
    def dependency(request: Request) -> None:
        identifier = (
            identifier_getter(request)
            if identifier_getter is not None
            else request.client.host if request.client else "unknown"
        )
        resolved_limit = limit() if callable(limit) else limit
        resolved_window = window_seconds() if callable(window_seconds) else window_seconds
        rate_limiter.enforce(
            f"{scope}:{identifier}",
            limit=resolved_limit,
            window_seconds=resolved_window,
        )

    return dependency
