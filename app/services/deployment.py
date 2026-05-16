from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.core.config import settings


def build_migration_preflight_payload() -> dict[str, object]:
    repo_root = Path(__file__).resolve().parents[2]
    alembic_ini = repo_root / "alembic.ini"

    try:
        config = Config(str(alembic_ini))
        script = ScriptDirectory.from_config(config)
        heads = list(script.get_heads())
    except Exception:
        heads = []

    return {
        "single_head": len(heads) == 1,
        "head_count": len(heads),
        "heads": heads,
    }


def build_deployment_status_payload() -> dict[str, object]:
    return {
        "environment": settings.APP_ENV,
        "service": settings.PROJECT_NAME,
        "production_safe": settings.is_production is False or settings.should_create_tables is False,
        "database": {
            "url_scheme": settings.DATABASE_URL.split(":", 1)[0],
            "auto_create_tables": settings.AUTO_CREATE_TABLES,
        },
        "redis": {
            "url_scheme": settings.REDIS_URL.split(":", 1)[0],
        },
        "jobs": {
            "enabled": settings.JOB_WORKER_ENABLED,
            "synchronous": settings.JOBS_SYNCHRONOUS,
            "max_retries": settings.JOB_WORKER_MAX_RETRIES,
        },
        "integrations": {
            "emails_enabled": settings.EMAILS_ENABLED,
            "smtp_configured": bool(settings.SMTP_HOST),
        },
        "migrations": build_migration_preflight_payload(),
    }
