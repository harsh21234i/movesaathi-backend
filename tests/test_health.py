from app.main import app


def test_health_endpoint_includes_request_context(client) -> None:
    response = client.get("/health", headers={"x-request-id": "health-req-1"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "health-req-1"
    assert response.json() == {
        "status": "ok",
        "service": "MooveSaathi",
        "environment": "development",
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
    }, True))

    response = client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"]["status"] == "ok"
    assert body["checks"]["redis"]["status"] == "ok"


def test_readiness_endpoint_returns_503_when_dependency_is_unavailable(client, monkeypatch) -> None:
    monkeypatch.setattr("app.main.build_readiness_payload", lambda: ({
        "status": "degraded",
        "service": "MooveSaathi",
        "environment": "test",
        "checks": {
            "database": {"status": "ok", "detail": "ok"},
            "redis": {"status": "error", "detail": "redis unavailable"},
        },
    }, False))

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["redis"]["status"] == "error"
