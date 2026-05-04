# MooveSaathi Backend

FastAPI backend for MooveSaathi, a role-based ride-sharing platform with rides, bookings, chat, notifications, audit logs, support tooling, and production-grade observability.

[![Backend CI](https://github.com/harsh21234i/movesaathi-backend/actions/workflows/backend-ci.yml/badge.svg)](https://github.com/harsh21234i/movesaathi-backend/actions/workflows/backend-ci.yml)

The backend follows a modular monolith structure:

- `app/api`: HTTP routes and dependency wiring
- `app/services`: business logic
- `app/repositories`: database access
- `app/models`: SQLAlchemy models
- `app/schemas`: request/response validation
- `app/websocket`: real-time chat connection management

## Highlights

- Role-based auth for `driver` and `passenger`
- Ride publishing, browsing, booking, and lifecycle management
- Booking-scoped realtime chat with Redis-backed fanout
- Notifications, audit trails, and support lookup tooling
- Metrics, request IDs, structured errors, and health checks
- SQLite-safe test and migration coverage for CI

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

## Production Deployment

Recommended order in production:

1. run a database backup
2. apply migrations with Alembic
3. verify `/health/ready`
4. start the API
5. monitor logs and error rate

Example:

```powershell
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

If a deployment must be rolled back:

1. stop the new API release
2. restore the previous application version
3. restore the database backup if the migration was not backward compatible
4. re-run readiness checks

Deployment rules:

- never enable `AUTO_CREATE_TABLES` in production
- never rely on SQLite in production
- keep `SECRET_KEY`, `DATABASE_URL`, and `REDIS_URL` explicitly configured
- use `/health/live` for liveness and `/health/ready` for dependency readiness

## Backup And Restore

For PostgreSQL, take a logical backup before running a migration or release:

```powershell
pg_dump -h <db-host> -U <db-user> -d moovesaathi -Fc -f moovesaathi.backup
```

Restore that backup if a deployment must be rolled back and the database
schema changed incompatibly:

```powershell
pg_restore -h <db-host> -U <db-user> -d moovesaathi --clean --if-exists moovesaathi.backup
```

Operational order for a risky deployment:

1. take a backup
2. run `alembic upgrade head`
3. start the new application version
4. verify `/health/ready`
5. if the deployment fails, stop the app and restore the backup before retrying

If you use containerized Postgres, backup/restore should run against the
database service directly instead of the API container.

## CI/CD Checklist

Current GitHub Actions flow:

1. install dependencies
2. validate imports with `python -m compileall app tests`
3. run `alembic upgrade head`
4. run the test suite

Release checklist:

- merge only after CI is green
- deploy database migrations before the new app version
- verify `/health/ready` after deployment
- monitor request logs, errors, and job retries
- keep a rollback window until the deployment is proven stable

Rollback checklist:

- stop the new release
- restore the previous app version
- restore the database backup if needed
- verify `/health/ready`
- re-run the test suite against the restored branch or environment if possible

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
- `EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES`
- `REQUIRE_EMAIL_VERIFICATION`
- `LOGIN_RATE_LIMIT_MAX_REQUESTS`
- `LOGIN_RATE_LIMIT_WINDOW_SECONDS`
- `FORGOT_PASSWORD_RATE_LIMIT_MAX_REQUESTS`
- `FORGOT_PASSWORD_RATE_LIMIT_WINDOW_SECONDS`
- `RESET_PASSWORD_RATE_LIMIT_MAX_REQUESTS`
- `RESET_PASSWORD_RATE_LIMIT_WINDOW_SECONDS`
- `RESEND_VERIFICATION_RATE_LIMIT_MAX_REQUESTS`
- `RESEND_VERIFICATION_RATE_LIMIT_WINDOW_SECONDS`
- `CHAT_MESSAGE_RATE_LIMIT_MAX_REQUESTS`
- `CHAT_MESSAGE_RATE_LIMIT_WINDOW_SECONDS`
- `REDIS_SOCKET_CONNECT_TIMEOUT`
- `REDIS_SOCKET_TIMEOUT`
- `EMAILS_ENABLED`
- `EMAIL_FROM`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_USE_TLS`
- `SMTP_USE_SSL`
- `FRONTEND_URL`
- `BACKEND_CORS_ORIGINS`
- `AUTO_CREATE_TABLES`

Production notes:

- `SECRET_KEY` must be overridden with a strong value
- `AUTO_CREATE_TABLES` should stay disabled in production
- set `EMAILS_ENABLED=true`, configure SMTP settings, and enable `REQUIRE_EMAIL_VERIFICATION=true` when you want verified-email login gating
- database schema changes should go through Alembic migrations

## Current Production Hardening

This backend now includes:

- safer environment validation for production settings
- migration-based schema management with Alembic
- request logging with request IDs
- transactional service writes for core flows
- uniqueness constraints for bookings and reviews
- refresh-token rotation and logout revocation
- email verification state and SMTP-backed verification delivery
- forgot-password and reset-password flows
- rate limiting for login, verification resend, password reset, and chat message writes
- Redis-backed safety controls with fast degraded-mode fallback
- API tests for auth, rides, bookings, config, and chat

## Remaining Work Before Large-Scale Production

Still recommended before real multi-instance scale:

- add background jobs for notifications/reminders
- expand rate limiting and abuse protection to more read/write surfaces
- move chat connection state to a fully distributed design
- add metrics, tracing, and centralized error reporting
- add CI/CD pipelines and staged deploys
- document backup/restore and rollback procedures in ops runbooks
