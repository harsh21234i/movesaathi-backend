# MooveSaathi Backend

FastAPI backend for the MooveSaathi ride-sharing platform.

The backend follows a modular monolith structure:

- `app/api`: HTTP routes and dependency wiring
- `app/services`: business logic
- `app/repositories`: database access
- `app/models`: SQLAlchemy models
- `app/schemas`: request/response validation
- `app/websocket`: real-time chat connection management

## Stack

- FastAPI
- SQLAlchemy 2.0
- Alembic
- PostgreSQL
- Redis
- JWT authentication
- WebSockets
- Pytest

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

## Docker

```powershell
docker compose up --build
```

The API container runs `alembic upgrade head` before starting the app.

## Testing

```powershell
pytest
```

## Environment

Important environment variables:

- `APP_ENV=development|test|production`
- `SECRET_KEY`
- `DATABASE_URL`
- `REDIS_URL`
- `REFRESH_TOKEN_EXPIRE_DAYS`
- `RESET_TOKEN_EXPIRE_MINUTES`
- `LOGIN_RATE_LIMIT_MAX_REQUESTS`
- `LOGIN_RATE_LIMIT_WINDOW_SECONDS`
- `FORGOT_PASSWORD_RATE_LIMIT_MAX_REQUESTS`
- `FORGOT_PASSWORD_RATE_LIMIT_WINDOW_SECONDS`
- `RESET_PASSWORD_RATE_LIMIT_MAX_REQUESTS`
- `RESET_PASSWORD_RATE_LIMIT_WINDOW_SECONDS`
- `CHAT_MESSAGE_RATE_LIMIT_MAX_REQUESTS`
- `CHAT_MESSAGE_RATE_LIMIT_WINDOW_SECONDS`
- `REDIS_SOCKET_CONNECT_TIMEOUT`
- `REDIS_SOCKET_TIMEOUT`
- `BACKEND_CORS_ORIGINS`
- `AUTO_CREATE_TABLES`

Production notes:

- `SECRET_KEY` must be overridden with a strong value
- `AUTO_CREATE_TABLES` should stay disabled in production
- database schema changes should go through Alembic migrations

## Current Production Hardening

This backend now includes:

- safer environment validation for production settings
- migration-based schema management with Alembic
- request logging with request IDs
- transactional service writes for core flows
- uniqueness constraints for bookings and reviews
- refresh-token rotation and logout revocation
- forgot-password and reset-password flows
- rate limiting for login, password reset, and chat message writes
- Redis-backed safety controls with fast degraded-mode fallback
- API tests for auth, rides, bookings, config, and chat

## Remaining Work Before Large-Scale Production

Still recommended before real multi-instance scale:

- add background jobs for notifications/reminders
- add email verification and outbound email delivery
- expand rate limiting and abuse protection to more read/write surfaces
- move chat connection state to a fully distributed design
- add metrics, tracing, and centralized error reporting
- add CI/CD pipelines and staged deploys
