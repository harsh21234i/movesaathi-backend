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
    assert body["items"][0]["driver_verification_status"] == "pending"


def test_support_can_approve_driver_verification_in_realtime(client, monkeypatch) -> None:
    monkeypatch.setattr("app.core.config.settings.SUPPORT_API_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.SUPPORT_API_KEY", "support-secret")
    published: list[dict[str, object]] = []

    def capture_publish(_service, user):
        published.append(
            {
                "user_id": user.id,
                "driver_verification_status": user.driver_verification_status.value,
            }
        )

    monkeypatch.setattr("app.services.support.SupportService._publish_driver_verification_event", capture_publish)

    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Approval Driver",
            "email": "approval-driver@example.com",
            "password": "Password123",
            "phone_number": "2222222222",
            "role": "driver",
        },
    )
    assert register_response.status_code == 201
    driver_id = register_response.json()["id"]
    driver_token = client.post(
        "/api/v1/auth/login",
        json={"email": "approval-driver@example.com", "password": "Password123"},
    ).json()["access_token"]
    support_headers = {"x-support-token": "support-secret"}

    pending = client.get("/api/v1/support/driver-verifications/pending", headers=support_headers)
    assert pending.status_code == 200
    assert pending.json()["items"][0]["id"] == driver_id

    review = client.patch(
        f"/api/v1/support/driver-verifications/{driver_id}",
        headers=support_headers,
        json={"status": "verified"},
    )

    assert review.status_code == 200
    assert review.json()["driver_verification_status"] == "verified"
    assert published == [{"user_id": driver_id, "driver_verification_status": "verified"}]

    notifications = client.get(
        "/api/v1/notifications",
        headers={"Authorization": f"Bearer {driver_token}"},
    )
    assert notifications.status_code == 200
    assert notifications.json()["items"][0]["type"] == "driver_verification_approved"


def test_support_rejects_driver_verification_with_reason(client, monkeypatch) -> None:
    monkeypatch.setattr("app.core.config.settings.SUPPORT_API_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.SUPPORT_API_KEY", "support-secret")
    monkeypatch.setattr("app.services.support.SupportService._publish_driver_verification_event", lambda *_args: None)

    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Rejected Driver",
            "email": "rejected-driver@example.com",
            "password": "Password123",
            "phone_number": "3333333333",
            "role": "driver",
        },
    )
    assert register_response.status_code == 201
    driver_id = register_response.json()["id"]

    missing_reason = client.patch(
        f"/api/v1/support/driver-verifications/{driver_id}",
        headers={"x-support-token": "support-secret"},
        json={"status": "rejected"},
    )
    assert missing_reason.status_code == 400

    rejected = client.patch(
        f"/api/v1/support/driver-verifications/{driver_id}",
        headers={"x-support-token": "support-secret"},
        json={"status": "rejected", "rejection_reason": "Vehicle plate photo is unreadable"},
    )

    assert rejected.status_code == 200
    assert rejected.json()["driver_verification_status"] == "rejected"
    assert rejected.json()["driver_verification_rejection_reason"] == "Vehicle plate photo is unreadable"
