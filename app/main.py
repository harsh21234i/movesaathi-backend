from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.headers import add_security_headers
from app.core.logging import configure_logging, log_requests
from app.db.session import initialize_database
from app.services.health import build_readiness_payload
from starlette.exceptions import HTTPException as StarletteHTTPException


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title=settings.PROJECT_NAME,
        version="1.0.0",
        description="MooveSaathi ride-sharing platform backend API.",
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.middleware("http")(log_requests)
    app.middleware("http")(add_security_headers)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    app.include_router(api_router, prefix=settings.API_V1_STR)

    @app.get("/health", tags=["health"])
    def health_check(request: Request) -> dict[str, str | None]:
        return {
            "status": "ok",
            "service": settings.PROJECT_NAME,
            "environment": settings.APP_ENV,
            "request_id": getattr(request.state, "request_id", None),
        }

    @app.get("/health/live", tags=["health"])
    def live_check(request: Request) -> dict[str, str | None]:
        return {
            "status": "ok",
            "service": settings.PROJECT_NAME,
            "environment": settings.APP_ENV,
            "request_id": getattr(request.state, "request_id", None),
        }

    @app.get("/health/ready", tags=["health"])
    def readiness_check() -> JSONResponse:
        payload, healthy = build_readiness_payload()
        return JSONResponse(
            status_code=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
            content=payload,
        )

    return app


app = create_app()
