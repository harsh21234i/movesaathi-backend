def test_support_lookup_requires_token(client, monkeypatch) -> None:
    monkeypatch.setattr("app.core.config.settings.SUPPORT_API_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.SUPPORT_API_KEY", "support-secret")

    response = client.get("/api/v1/support/users/1")

    assert response.status_code == 401


def test_support_lookup_returns_user_with_audit_summary(client, monkeypatch) -> None:
    monkeypatch.setattr("app.core.config.settings.SUPPORT_API_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.SUPPORT_API_KEY", "support-secret")

    client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Support User",
            "email": "support-user@example.com",
            "password": "Password123",
            "phone_number": "1111111111",
            "role": "driver",
        },
    )
    headers = {"x-support-token": "support-secret"}

    response = client.get("/api/v1/support/users?email=support-user@example.com", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["items"]
    assert body["items"][0]["email"] == "support-user@example.com"
    assert body["items"][0]["audit_summary"]["total"] >= 1
