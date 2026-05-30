from app.core.config import settings


def test_deployment_status_reports_runtime_flags(client) -> None:
    response = client.get("/api/v1/deployment/status")

    assert response.status_code == 200
    body = response.json()
    assert body["environment"] == settings.APP_ENV
    assert body["service"] == "MooveSaathi"
    assert body["release"]["version"] == settings.APP_VERSION
    assert body["release"]["build_sha"] is None
    assert body["release"]["build_timestamp"] is None
    assert body["database"]["auto_create_tables"] == settings.AUTO_CREATE_TABLES
    assert body["jobs"]["enabled"] == settings.JOB_WORKER_ENABLED
    assert body["integrations"]["emails_enabled"] == settings.EMAILS_ENABLED
    assert body["integrations"]["smtp_configured"] is False
    assert body["migrations"]["head_count"] >= 1
    assert body["migrations"]["single_head"] is True
    assert body["migrations"]["rollback_safe"] is True
    assert len(body["migrations"]["heads"]) == body["migrations"]["head_count"]
    assert body["rollback"]["safe"] is True
    assert body["rollback"]["reasons"] == []
    assert body["preflight"]["ready_to_deploy"] is True
    assert body["preflight"]["rollback_safe"] is True
    assert body["preflight"]["rollback"]["safe"] is True
    assert body["preflight"]["blocking_issues"] == []
    assert body["preflight"]["checks"]["migrations_single_head"] is True
    assert body["preflight"]["checks"]["error_reporting_configured_when_enabled"] is True
    assert body["preflight"]["checks"]["support_api_configured_when_enabled"] is True


def test_deployment_status_is_not_production_safe_in_development(client) -> None:
    response = client.get("/api/v1/deployment/status")

    assert response.status_code == 200
    assert response.json()["production_safe"] is True


def test_migration_preflight_reports_the_current_heads() -> None:
    from app.services.deployment import build_migration_preflight_payload

    payload = build_migration_preflight_payload()

    assert isinstance(payload["heads"], list)
    assert payload["head_count"] == len(payload["heads"])
    assert payload["single_head"] == (payload["head_count"] == 1)


def test_deployment_preflight_endpoint_returns_gateable_contract(client) -> None:
    response = client.get("/api/v1/deployment/preflight")

    assert response.status_code == 200
    body = response.json()
    assert body["ready_to_deploy"] is True
    assert body["blocking_issues"] == []
    assert body["migrations"]["single_head"] is True
    assert body["runtime_dependencies_healthy"] is True


def test_deployment_preflight_blocks_when_dependencies_are_unhealthy(monkeypatch) -> None:
    from app.services.deployment import build_deployment_preflight_payload

    payload = build_deployment_preflight_payload(
        readiness_check=lambda: (
            {
                "status": "degraded",
                "service": "MooveSaathi",
                "environment": "test",
                "checks": {
                    "database": {"status": "ok", "detail": "ok"},
                    "redis": {"status": "error", "detail": "redis unavailable"},
                },
            },
            False,
        )
    )

    assert payload["ready_to_deploy"] is False
    assert payload["rollback_safe"] is False
    assert "runtime-dependencies-unhealthy" in payload["blocking_issues"]
    assert payload["checks"]["runtime_dependencies_healthy"] is False


def test_deployment_preflight_blocks_when_error_reporting_or_support_is_misconfigured(monkeypatch) -> None:
    monkeypatch.setattr("app.services.deployment.settings.ERROR_REPORTING_ENABLED", True)
    monkeypatch.setattr("app.services.deployment.settings.ERROR_REPORTING_DSN", None)
    monkeypatch.setattr("app.services.deployment.settings.SUPPORT_API_ENABLED", True)
    monkeypatch.setattr("app.services.deployment.settings.SUPPORT_API_KEY", None)

    from app.services.deployment import build_deployment_preflight_payload

    payload = build_deployment_preflight_payload(
        readiness_check=lambda: (
            {
                "status": "ok",
                "service": "MooveSaathi",
                "environment": "test",
                "checks": {
                    "database": {"status": "ok", "detail": "ok"},
                    "redis": {"status": "ok", "detail": "ok"},
                },
            },
            True,
        )
    )

    assert payload["ready_to_deploy"] is False
    assert "error-reporting-missing-dsn" in payload["blocking_issues"]
    assert "support-api-missing-key" in payload["blocking_issues"]
    assert payload["checks"]["error_reporting_configured_when_enabled"] is False
    assert payload["checks"]["support_api_configured_when_enabled"] is False


def test_deployment_checklist_endpoint_returns_release_steps(client) -> None:
    response = client.get("/api/v1/deployment/checklist")

    assert response.status_code == 200
    body = response.json()
    assert body["release"]["version"] == settings.APP_VERSION
    assert body["guards"]["single_migration_head"] is True
    assert body["guards"]["runtime_dependencies_healthy"] is True
    assert body["guards"]["ready_to_deploy"] is True
    assert body["guards"]["rollback_safe"] is True
    assert body["rollback"]["safe"] is True
    assert body["rollback"]["reasons"] == []
    assert "run alembic upgrade head" in body["deploy_steps"]
    assert "restore the database backup" in " ".join(body["rollback_steps"])


def test_deployment_preflight_reports_rollback_unsafety_for_multiple_heads(monkeypatch) -> None:
    from app.services.deployment import build_deployment_preflight_payload

    monkeypatch.setattr(
        "app.services.deployment.build_migration_preflight_payload",
        lambda: {"single_head": False, "head_count": 2, "heads": ["head-a", "head-b"], "rollback_safe": False},
    )

    payload = build_deployment_preflight_payload(
        readiness_check=lambda: (
            {
                "status": "ok",
                "service": "MooveSaathi",
                "environment": "test",
                "checks": {
                    "database": {"status": "ok", "detail": "ok"},
                    "redis": {"status": "ok", "detail": "ok"},
                },
            },
            True,
        )
    )

    assert payload["rollback_safe"] is False
    assert payload["rollback"]["safe"] is False
    assert "alembic-multiple-heads" in payload["blocking_issues"]
    assert "multiple-alembic-heads" in payload["rollback"]["reasons"]
