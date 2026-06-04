from datetime import datetime, timezone
from threading import Lock
from dataclasses import dataclass
from collections.abc import Iterable

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings


@dataclass(slots=True)
class SessionRecord:
    jti: str
    user_id: int
    issued_at: datetime
    expires_at: datetime
    user_agent: str | None = None
    ip_address: str | None = None


class TokenStore:
    def __init__(self) -> None:
        self._client = Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
        )
        self._in_memory_tokens: dict[str, datetime] = {}
        self._in_memory_sessions: dict[str, SessionRecord] = {}
        self._in_memory_user_sessions: dict[int, set[str]] = {}
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
        except (RedisError, AttributeError):
            pass

        with self._lock:
            self._prune_expired()
            return jti in self._in_memory_tokens

    def register_session(
        self,
        *,
        user_id: int,
        jti: str,
        issued_at: datetime,
        expires_at: datetime,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> None:
        issued_at = self._normalize(issued_at)
        expires_at = self._normalize(expires_at)
        try:
            key = self._session_key(jti)
            self._client.hset(
                key,
                mapping={
                    "user_id": str(user_id),
                    "issued_at": issued_at.isoformat(),
                    "expires_at": expires_at.isoformat(),
                    "user_agent": user_agent or "",
                    "ip_address": ip_address or "",
                },
            )
            ttl_seconds = max(int((expires_at - datetime.now(timezone.utc)).total_seconds()), 1)
            self._client.expire(key, ttl_seconds)
            self._client.sadd(self._user_sessions_key(user_id), jti)
            self._client.expire(self._user_sessions_key(user_id), ttl_seconds)
            return
        except (RedisError, AttributeError):
            pass

        with self._lock:
            self._in_memory_sessions[jti] = SessionRecord(
                jti=jti,
                user_id=user_id,
                issued_at=issued_at,
                expires_at=expires_at,
                user_agent=user_agent,
                ip_address=ip_address,
            )
            self._in_memory_user_sessions.setdefault(user_id, set()).add(jti)
            self._prune_expired()

    def get_session(self, jti: str) -> SessionRecord | None:
        try:
            data = self._client.hgetall(self._session_key(jti))
            if not data:
                return None
            return SessionRecord(
                jti=jti,
                user_id=int(data["user_id"]),
                issued_at=datetime.fromisoformat(data["issued_at"]),
                expires_at=datetime.fromisoformat(data["expires_at"]),
                user_agent=data.get("user_agent") or None,
                ip_address=data.get("ip_address") or None,
            )
        except (RedisError, AttributeError, KeyError, ValueError):
            pass

        with self._lock:
            self._prune_expired()
            return self._in_memory_sessions.get(jti)

    def list_sessions(self, user_id: int) -> list[SessionRecord]:
        try:
            jtis = self._client.smembers(self._user_sessions_key(user_id))
            sessions: list[SessionRecord] = []
            for jti in jtis:
                data = self._client.hgetall(self._session_key(jti))
                if not data:
                    continue
                sessions.append(
                    SessionRecord(
                        jti=jti,
                        user_id=int(data["user_id"]),
                        issued_at=datetime.fromisoformat(data["issued_at"]),
                        expires_at=datetime.fromisoformat(data["expires_at"]),
                        user_agent=data.get("user_agent") or None,
                        ip_address=data.get("ip_address") or None,
                    )
                )
            return sorted(sessions, key=lambda item: item.issued_at, reverse=True)
        except (RedisError, AttributeError):
            pass

        with self._lock:
            self._prune_expired()
            sessions = [record for record in self._in_memory_sessions.values() if record.user_id == user_id]
            return sorted(sessions, key=lambda item: item.issued_at, reverse=True)

    def revoke_session(self, jti: str) -> None:
        expires_at: datetime | None = None
        try:
            self._client.delete(self._session_key(jti))
            for key in self._client.keys(self._user_sessions_key("*")):
                self._client.srem(key, jti)
            return
        except (RedisError, AttributeError):
            pass

        with self._lock:
            record = self._in_memory_sessions.pop(jti, None)
            if not record:
                return
            expires_at = record.expires_at
            sessions = self._in_memory_user_sessions.get(record.user_id)
            if sessions:
                sessions.discard(jti)
                if not sessions:
                    self._in_memory_user_sessions.pop(record.user_id, None)

        if expires_at:
            self.revoke(jti, expires_at)

    def revoke_user_sessions(self, user_id: int) -> None:
        try:
            sessions = self._client.smembers(self._user_sessions_key(user_id))
            for jti in sessions:
                data = self._client.hgetall(self._session_key(jti))
                expires_at = datetime.fromisoformat(data["expires_at"]) if data else datetime.now(timezone.utc)
                self.revoke(jti, expires_at)
                self._client.delete(self._session_key(jti))
            self._client.delete(self._user_sessions_key(user_id))
            return
        except (RedisError, AttributeError):
            pass

        records_to_revoke: list[tuple[str, datetime]] = []
        with self._lock:
            jtis = self._in_memory_user_sessions.pop(user_id, set())
            for jti in jtis:
                record = self._in_memory_sessions.pop(jti, None)
                if record:
                    records_to_revoke.append((jti, record.expires_at))

        for jti, expires_at in records_to_revoke:
            self.revoke(jti, expires_at)

    def revoke_user_sessions_except(self, user_id: int, keep_jti: str | None) -> None:
        try:
            sessions = self._client.smembers(self._user_sessions_key(user_id))
            for jti in sessions:
                if jti == keep_jti:
                    continue
                data = self._client.hgetall(self._session_key(jti))
                expires_at = datetime.fromisoformat(data["expires_at"]) if data else datetime.now(timezone.utc)
                self.revoke(jti, expires_at)
                self._client.delete(self._session_key(jti))
            if keep_jti is None:
                self._client.delete(self._user_sessions_key(user_id))
            else:
                self._client.sadd(self._user_sessions_key(user_id), keep_jti)
            return
        except (RedisError, AttributeError):
            pass

        records_to_revoke: list[tuple[str, datetime]] = []
        with self._lock:
            sessions = self._in_memory_user_sessions.get(user_id, set()).copy()
            for jti in sessions:
                if jti == keep_jti:
                    continue
                record = self._in_memory_sessions.pop(jti, None)
                if record:
                    records_to_revoke.append((jti, record.expires_at))
            if keep_jti is None:
                self._in_memory_user_sessions.pop(user_id, None)
            else:
                self._in_memory_user_sessions[user_id] = {keep_jti}

        for jti, expires_at in records_to_revoke:
            self.revoke(jti, expires_at)

    def _prune_expired(self) -> None:
        now = datetime.now(timezone.utc)
        self._in_memory_tokens = {
            jti: expires_at for jti, expires_at in self._in_memory_tokens.items() if expires_at > now
        }
        for jti, record in list(self._in_memory_sessions.items()):
            if record.expires_at <= now:
                self._in_memory_sessions.pop(jti, None)
                sessions = self._in_memory_user_sessions.get(record.user_id)
                if sessions:
                    sessions.discard(jti)
                    if not sessions:
                        self._in_memory_user_sessions.pop(record.user_id, None)

    def _redis_key(self, jti: str) -> str:
        return f"token:blacklist:{jti}"

    def _session_key(self, jti: str) -> str:
        return f"token:session:{jti}"

    def _user_sessions_key(self, user_id: int | str) -> str:
        return f"token:sessions:{user_id}"

    def _normalize(self, expires_at: datetime) -> datetime:
        if expires_at.tzinfo is None:
            return expires_at.replace(tzinfo=timezone.utc)
        return expires_at.astimezone(timezone.utc)


token_store = TokenStore()
