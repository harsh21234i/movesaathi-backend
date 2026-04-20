from __future__ import annotations

from collections.abc import Callable

from fastapi import Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.services.idempotency import idempotency_store


async def idempotent_execute(
    *,
    request: Request,
    actor_id: int | None,
    callback: Callable[[], object],
    serializer: Callable[[object], object] | None = None,
    status_code: int = 200,
) -> Response:
    idempotency_state = await idempotency_store.get_cached_response(request, actor_id)
    if idempotency_state is not None:
        record_key, record = idempotency_state
        if record.status_code != 0:
            if record.body is None:
                return Response(status_code=record.status_code, headers={"x-idempotent-replay": "true"})
            return JSONResponse(
                status_code=record.status_code,
                content=record.body,
                headers={"x-idempotent-replay": "true"},
            )
    else:
        record_key = None
        record = None

    result = callback()

    if serializer is None:
        body = jsonable_encoder(result)
    else:
        body = jsonable_encoder(serializer(result))

    if record_key is not None and record is not None:
        idempotency_store.save_response(
            record_key,
            request_hash=record.request_hash,
            status_code=status_code,
            body=body,
        )

    return JSONResponse(status_code=status_code, content=body)
