import logging

from fastapi import HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _error_code_for_status(status_code: int) -> str:
    mapping = {
        status.HTTP_400_BAD_REQUEST: "bad_request",
        status.HTTP_401_UNAUTHORIZED: "unauthorized",
        status.HTTP_403_FORBIDDEN: "forbidden",
        status.HTTP_404_NOT_FOUND: "not_found",
        status.HTTP_409_CONFLICT: "conflict",
        status.HTTP_422_UNPROCESSABLE_ENTITY: "validation_error",
        status.HTTP_429_TOO_MANY_REQUESTS: "rate_limited",
    }
    return mapping.get(status_code, "http_error")


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    content = {
        "detail": exc.detail,
        "code": _error_code_for_status(exc.status_code),
        "request_id": _request_id(request),
    }
    return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    content = {
        "detail": "Request validation failed",
        "code": "validation_error",
        "request_id": _request_id(request),
        "errors": jsonable_encoder(exc.errors()),
    }
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=content)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logging.getLogger("app.error").exception("Unhandled exception request_id=%s", _request_id(request), exc_info=exc)
    content = {
        "detail": "Internal server error",
        "code": "internal_server_error",
        "request_id": _request_id(request),
    }
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=content)
