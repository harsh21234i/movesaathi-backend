from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from threading import Lock

from fastapi import HTTPException, Request, status
from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings


@dataclass
class IdempotencyRecord:
    request_hash: str
    status_code: int
    body: object | None


class IdempotencyStore:
    def __init__(self) -> None:
        self._client = Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
        )
        self._memory: dict[str, IdempotencyRecord] = {}
        self._lock = Lock()

    async def get_cached_response(self, request: Request, actor_id: int | None) -> tuple[str, IdempotencyRecord] | None:
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return None

        record_key = self._build_key(
            method=request.method,
            path=request.url.path,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
        )
        request_hash = self._request_hash(await request.body())
        record = self._get(record_key)
        if record is None:
            return record_key, IdempotencyRecord(request_hash=request_hash, status_code=0, body=None)
        if record.request_hash != request_hash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Idempotency key reuse with different request payload",
            )
        return record_key, record

    def save_response(self, record_key: str, request_hash: str, status_code: int, body: object | None) -> None:
        record = IdempotencyRecord(request_hash=request_hash, status_code=status_code, body=body)
        ttl = settings.IDEMPOTENCY_KEY_TTL_SECONDS
        payload = json.dumps(
            {
                "request_hash": record.request_hash,
                "status_code": record.status_code,
                "body": record.body,
            }
        )

        try:
            self._client.setex(record_key, ttl, payload)
            return
        except RedisError:
            pass

        with self._lock:
            self._memory[record_key] = record

    def reset(self) -> None:
        with self._lock:
            self._memory.clear()

    def _get(self, record_key: str) -> IdempotencyRecord | None:
        try:
            payload = self._client.get(record_key)
            if payload:
                data = json.loads(payload)
                return IdempotencyRecord(
                    request_hash=data["request_hash"],
                    status_code=int(data["status_code"]),
                    body=data.get("body"),
                )
        except RedisError:
            pass

        with self._lock:
            return self._memory.get(record_key)

    def _build_key(self, *, method: str, path: str, actor_id: int | None, idempotency_key: str) -> str:
        scope = actor_id if actor_id is not None else "anonymous"
        return f"idempotency:{scope}:{method}:{path}:{idempotency_key}"

    def _request_hash(self, body: bytes) -> str:
        return hashlib.sha256(body).hexdigest()


idempotency_store = IdempotencyStore()
