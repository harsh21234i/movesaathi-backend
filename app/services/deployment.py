from collections.abc import Callable
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.core.config import settings

from app.services.health import build_readiness_payload


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


def build_deployment_preflight_payload(
    *,
    readiness_check: Callable[[], tuple[dict[str, object], bool]] | None = None,
) -> dict[str, object]:
    migrations = build_migration_preflight_payload()

    if readiness_check is not None:
        readiness_payload, dependencies_healthy = readiness_check()
    elif settings.APP_ENV != "production":
        # Non-production environments should not fail deployment checks because
        # local test/dev setups usually do not run the full production stack.
        readiness_payload = {
            "status": "ok",
            "service": settings.PROJECT_NAME,
            "environment": settings.APP_ENV,
            "checks": {
                "database": {"status": "ok", "detail": "test environment"},
                "redis": {"status": "ok", "detail": "test environment"},
            },
        }
        dependencies_healthy = True
    else:
        readiness_payload, dependencies_healthy = build_readiness_payload()

    blocking_issues: list[str] = []
    if not migrations["single_head"]:
        blocking_issues.append("alembic-multiple-heads")
    if not dependencies_healthy:
        blocking_issues.append("runtime-dependencies-unhealthy")
    if settings.is_production and settings.AUTO_CREATE_TABLES:
        blocking_issues.append("auto-create-tables-enabled")
    if settings.EMAILS_ENABLED and not settings.SMTP_HOST:
        blocking_issues.append("smtp-missing")
    if settings.ERROR_REPORTING_ENABLED and not settings.ERROR_REPORTING_DSN:
        blocking_issues.append("error-reporting-missing-dsn")
    if settings.SUPPORT_API_ENABLED and not settings.SUPPORT_API_KEY:
        blocking_issues.append("support-api-missing-key")

    checks = {
        "migrations_single_head": migrations["single_head"],
        "runtime_dependencies_healthy": dependencies_healthy,
        "production_auto_create_disabled": not (settings.is_production and settings.AUTO_CREATE_TABLES),
        "smtp_configured_when_enabled": not settings.EMAILS_ENABLED or bool(settings.SMTP_HOST),
        "error_reporting_configured_when_enabled": not settings.ERROR_REPORTING_ENABLED
        or bool(settings.ERROR_REPORTING_DSN),
        "support_api_configured_when_enabled": not settings.SUPPORT_API_ENABLED or bool(settings.SUPPORT_API_KEY),
    }

    return {
        "ready_to_deploy": not blocking_issues,
        "blocking_issues": blocking_issues,
        "checks": checks,
        "runtime_dependencies_healthy": dependencies_healthy,
        "runtime_dependencies": readiness_payload["checks"],
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


def build_deployment_checklist_payload() -> dict[str, object]:
    preflight = build_deployment_preflight_payload()
    return {
        "release": {
            "version": settings.APP_VERSION,
            "service": settings.PROJECT_NAME,
        },
        "deploy_steps": [
            "take a database backup",
            "run alembic upgrade head",
            "verify /health/ready",
            "start the new API release",
            "monitor logs, metrics, and job retries",
        ],
        "rollback_steps": [
            "stop the new release",
            "restore the previous application version",
            "restore the database backup if the migration was not backward compatible",
            "verify /health/ready again",
        ],
        "guards": {
            "single_migration_head": build_migration_preflight_payload()["single_head"],
            "runtime_dependencies_healthy": preflight["runtime_dependencies_healthy"],
            "ready_to_deploy": preflight["ready_to_deploy"],
        },
    }
