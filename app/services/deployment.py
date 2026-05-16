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


def build_deployment_preflight_payload() -> dict[str, object]:
    migrations = build_migration_preflight_payload()

    blocking_issues: list[str] = []
    if not migrations["single_head"]:
        blocking_issues.append("alembic-multiple-heads")
    if settings.is_production and settings.AUTO_CREATE_TABLES:
        blocking_issues.append("auto-create-tables-enabled")
    if settings.EMAILS_ENABLED and not settings.SMTP_HOST:
        blocking_issues.append("smtp-missing")

    checks = {
        "migrations_single_head": migrations["single_head"],
        "production_auto_create_disabled": not (settings.is_production and settings.AUTO_CREATE_TABLES),
        "smtp_configured_when_enabled": not settings.EMAILS_ENABLED or bool(settings.SMTP_HOST),
    }

    return {
        "ready_to_deploy": not blocking_issues,
        "blocking_issues": blocking_issues,
        "checks": checks,
        "migrations": migrations,
    }


def build_deployment_status_payload() -> dict[str, object]:
    return {
        "environment": settings.APP_ENV,
        "service": settings.PROJECT_NAME,
        "release": {
            "version": settings.APP_VERSION,
            "build_sha": settings.BUILD_SHA,
            "build_timestamp": settings.BUILD_TIMESTAMP,
        },
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
        "preflight": build_deployment_preflight_payload(),
    }
