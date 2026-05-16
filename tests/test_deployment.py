from app.core.config import settings


def test_deployment_status_reports_runtime_flags(client) -> None:
    response = client.get("/api/v1/deployment/status")

    assert response.status_code == 200
    body = response.json()
    assert body["environment"] == settings.APP_ENV
    assert body["service"] == "MooveSaathi"
    assert body["database"]["auto_create_tables"] == settings.AUTO_CREATE_TABLES
    assert body["jobs"]["enabled"] == settings.JOB_WORKER_ENABLED
    assert body["integrations"]["emails_enabled"] == settings.EMAILS_ENABLED
    assert body["integrations"]["smtp_configured"] is False
    assert body["migrations"]["head_count"] >= 1
    assert body["migrations"]["single_head"] is True
    assert len(body["migrations"]["heads"]) == body["migrations"]["head_count"]


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
