from fastapi.testclient import TestClient

from app.main import app


def test_development_frontend_origins_pass_cors_preflight() -> None:
    for origin in (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://192.168.1.20:5173",
        "http://localhost:4173",
        "http://localhost:5174",
        "http://127.0.0.1:3000",
        "http://192.168.1.20:8080",
    ):
        response = TestClient(app).options(
            "/api/v1/auth/login",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin


def test_public_development_origin_does_not_pass_cors_preflight() -> None:
    response = TestClient(app).options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://example.com:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
