from app.core.config import settings


def test_health_endpoint_includes_request_context(client) -> None:
    response = client.get("/health", headers={"x-request-id": "health-req-1"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "health-req-1"
    assert response.json() == {
        "status": "ok",
        "service": "MooveSaathi",
        "environment": settings.APP_ENV,
        "request_id": "health-req-1",
    }


def test_readiness_endpoint_reports_dependency_statuses(client, monkeypatch) -> None:
    monkeypatch.setattr("app.main.build_readiness_payload", lambda: ({
        "status": "ok",
        "service": "MooveSaathi",
        "environment": "test",
        "checks": {
            "database": {"status": "ok", "detail": "ok"},
            "redis": {"status": "ok", "detail": "ok"},
        },
        "dependencies": {"database": True, "redis": True},
        "generated_at": "2026-05-16T00:00:00+00:00",
    }, True))

    response = client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"]["status"] == "ok"
    assert body["checks"]["redis"]["status"] == "ok"
    assert body["dependencies"] == {"database": True, "redis": True}
    assert body["generated_at"]


def test_readiness_endpoint_returns_503_when_dependency_is_unavailable(client, monkeypatch) -> None:
    monkeypatch.setattr("app.main.build_readiness_payload", lambda: ({
        "status": "degraded",
        "service": "MooveSaathi",
        "environment": "test",
        "checks": {
            "database": {"status": "ok", "detail": "ok"},
            "redis": {"status": "error", "detail": "redis unavailable"},
        },
        "dependencies": {"database": True, "redis": False},
        "generated_at": "2026-05-16T00:00:00+00:00",
    }, False))

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["redis"]["status"] == "error"
    assert response.json()["dependencies"] == {"database": True, "redis": False}
