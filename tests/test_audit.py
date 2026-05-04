from datetime import datetime, timedelta, timezone

from app.models.audit_log import AuditLog
from app.models.user import User
from app.services.audit_log import AuditLogService


def test_audit_endpoint_returns_current_user_logs(client) -> None:
    client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Audit Driver",
            "email": "audit-driver@example.com",
            "password": "Password123",
            "phone_number": "1111111111",
            "role": "driver",
        },
    )
    login = client.post("/api/v1/auth/login", json={"email": "audit-driver@example.com", "password": "Password123"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/v1/audit/me", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["items"]
    assert any(item["action"] == "user_registered" for item in body["items"])


def test_audit_logs_capture_sensitive_actions(client) -> None:
    register = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Audit Passenger",
            "email": "audit-passenger@example.com",
            "password": "Password123",
            "phone_number": "1111111111",
            "role": "passenger",
        },
    )
    token = register.json()["verification_token"]

    response = client.post("/api/v1/auth/verify-email", json={"token": token})
    assert response.status_code == 204

    login = client.post("/api/v1/auth/login", json={"email": "audit-passenger@example.com", "password": "Password123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    logs = client.get("/api/v1/audit/me", headers=headers)
    actions = [item["action"] for item in logs.json()["items"]]
    assert "email_verified" in actions
    assert "user_logged_in" in actions


def test_audit_summary_groups_activity(client) -> None:
    client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Summary User",
            "email": "summary-user@example.com",
            "password": "Password123",
            "phone_number": "1111111111",
            "role": "passenger",
        },
    )
    login = client.post("/api/v1/auth/login", json={"email": "summary-user@example.com", "password": "Password123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.get("/api/v1/audit/me/summary", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 2
    assert body["by_action"]["user_registered"] >= 1
    assert body["by_action"]["user_logged_in"] >= 1
    assert body["by_severity"]["info"] >= 1
    assert body["recent_items"]


def test_audit_cleanup_removes_old_records_only_for_current_user(client, db_session) -> None:
    client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Cleanup User",
            "email": "cleanup-user@example.com",
            "password": "Password123",
            "phone_number": "1111111111",
            "role": "driver",
        },
    )
    login = client.post("/api/v1/auth/login", json={"email": "cleanup-user@example.com", "password": "Password123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    user = db_session.query(User).filter(User.email == "cleanup-user@example.com").one()
    db_session.add(
        AuditLog(
            actor_user_id=user.id,
            action="old_action",
            severity="info",
            created_at=datetime.now(timezone.utc) - timedelta(days=400),
        )
    )
    db_session.commit()

    response = client.delete("/api/v1/audit/me/cleanup?keep_days=365", headers=headers)

    assert response.status_code == 200
    assert response.json()["deleted"] == 1
