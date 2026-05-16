from __future__ import annotations

import logging

from fastapi import Request

from app.core.config import settings


def report_exception(request: Request, exc: Exception) -> None:
    if not getattr(settings, "ERROR_REPORTING_ENABLED", False):
        return
    logging.getLogger("app.error_reporting").error(
        "Captured exception request_id=%s method=%s path=%s exception_type=%s",
        getattr(request.state, "request_id", None),
        request.method,
        request.url.path,
        exc.__class__.__name__,
        extra={
            "request_id": getattr(request.state, "request_id", None),
            "method": request.method,
            "path": request.url.path,
            "exception_type": exc.__class__.__name__,
        },
        exc_info=exc,
    )
