# MooveSaathi Backend

FastAPI backend for the MooveSaathi ride-sharing platform. The codebase follows a modular monolith structure with layered boundaries across routers, services, repositories, and models.

## Stack

- FastAPI
- SQLAlchemy 2.0
- PostgreSQL
- Redis
- JWT authentication
- WebSockets

## Run Locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

## Run With Docker

```powershell
docker compose up --build
```
