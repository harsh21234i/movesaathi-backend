from datetime import datetime, timezone
from threading import Lock

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings


class TokenStore:
    def __init__(self) -> None:
        self._client = Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
        )
        self._in_memory_tokens: dict[str, datetime] = {}
        self._lock = Lock()

    def revoke(self, jti: str, expires_at: datetime) -> None:
        expires_at = self._normalize(expires_at)
        ttl_seconds = max(int((expires_at - datetime.now(timezone.utc)).total_seconds()), 1)

        try:
            self._client.setex(self._redis_key(jti), ttl_seconds, "revoked")
            return
        except RedisError:
            pass

        with self._lock:
            self._in_memory_tokens[jti] = expires_at
            self._prune_expired()

    def is_revoked(self, jti: str) -> bool:
        try:
            return bool(self._client.exists(self._redis_key(jti)))
        except RedisError:
            pass

        with self._lock:
            self._prune_expired()
            return jti in self._in_memory_tokens

    def _prune_expired(self) -> None:
        now = datetime.now(timezone.utc)
        self._in_memory_tokens = {
            jti: expires_at for jti, expires_at in self._in_memory_tokens.items() if expires_at > now
        }

    def _redis_key(self, jti: str) -> str:
        return f"token:blacklist:{jti}"

    def _normalize(self, expires_at: datetime) -> datetime:
        if expires_at.tzinfo is None:
            return expires_at.replace(tzinfo=timezone.utc)
        return expires_at.astimezone(timezone.utc)


token_store = TokenStore()
