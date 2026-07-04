def test_health_check(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "MooveSaathi"
    from app.core.config import settings

    assert body["environment"] == settings.APP_ENV
    assert body["request_id"]


def test_register_login_and_me(client) -> None:
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Test User",
            "email": "test@example.com",
            "password": "Password123",
            "phone_number": "9999999999",
        },
    )
    assert register_response.status_code == 201
    assert register_response.json()["email"] == "test@example.com"
    assert register_response.json()["email_verified"] is False
    assert register_response.json()["verification_token"]

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "Password123"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    refresh_token = login_response.json()["refresh_token"]
    assert refresh_token

    me_response = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "test@example.com"


def test_register_queues_verification_email_without_waiting_on_delivery(client, monkeypatch) -> None:
    queued: list[str] = []

    monkeypatch.setattr("app.services.auth.job_queue.enqueue", lambda job: queued.append(job.name))

    response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Queue User",
            "email": "queue@example.com",
            "password": "Password123",
            "phone_number": "9999999999",
            "role": "driver",
        },
    )

    assert response.status_code == 201
    assert queued == ["send-verification-email:1"]


def test_forgot_password_queues_reset_email_without_waiting_on_delivery(client, monkeypatch) -> None:
    queued: list[str] = []

    monkeypatch.setattr("app.services.auth.job_queue.enqueue", lambda job: queued.append(job.name))

    response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Reset Queue User",
            "email": "reset-queue@example.com",
            "password": "Password123",
            "phone_number": "9999999999",
            "role": "driver",
        },
    )
    assert response.status_code == 201

    forgot_response = client.post("/api/v1/auth/forgot-password", json={"email": "reset-queue@example.com"})

    assert forgot_response.status_code == 200
    assert queued == [
        "send-verification-email:1",
        "send-reset-password-email:1",
    ]
    assert forgot_response.json()["reset_token"]


def test_change_password_queues_session_cleanup(client, monkeypatch) -> None:
    queued: list[str] = []
    monkeypatch.setattr("app.services.auth.job_queue.enqueue", lambda job: queued.append(job.name))

    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Cleanup User",
            "email": "cleanup@example.com",
            "password": "Password123",
            "phone_number": "1111111111",
        },
    )
    assert register_response.status_code == 201

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "cleanup@example.com", "password": "Password123"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    change_response = client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "Password123", "new_password": "NewPassword123"},
    )

    assert change_response.status_code == 204
    assert "session-cleanup:1" in queued


def test_register_rejects_duplicate_email(client) -> None:
    payload = {
        "full_name": "Test User",
        "email": "duplicate@example.com",
        "password": "Password123",
        "phone_number": "9999999999",
    }

    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    duplicate_response = client.post("/api/v1/auth/register", json=payload)

    assert duplicate_response.status_code == 400
    assert duplicate_response.json()["detail"] == "Email already in use"


def test_register_rejects_weak_password(client) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Weak Password User",
            "email": "weak@example.com",
            "password": "passwordonly",
            "phone_number": "9999999999",
        },
    )

    assert response.status_code == 422


def test_account_security_reports_lockout_state(client, db_session) -> None:
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Lockout User",
            "email": "lockout@example.com",
            "password": "Password123",
            "phone_number": "2222222222",
        },
    )
    assert register_response.status_code == 201

    from datetime import datetime, timedelta, timezone

    from app.repositories.user import UserRepository
    from app.services.auth import AuthService

    user = UserRepository(db_session).get_by_email("lockout@example.com")
    assert user is not None
    user.failed_login_attempts = 3
    user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
    db_session.commit()

    account_security = AuthService(db_session).account_security(user)
    assert account_security.is_locked is True
    assert account_security.failed_login_attempts == 3
    assert account_security.lockout_reason


def test_failed_login_and_lockout_are_audited_and_metered(client, db_session, monkeypatch) -> None:
    from app.repositories.audit_log import AuditLogRepository

    monkeypatch.setattr("app.services.auth.settings.AUTH_MAX_FAILED_LOGIN_ATTEMPTS", 2)

    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Audit Login User",
            "email": "audit-login@example.com",
            "password": "Password123",
            "phone_number": "2323232323",
        },
    )
    assert register_response.status_code == 201

    for _ in range(2):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "audit-login@example.com", "password": "WrongPassword123"},
        )
        assert response.status_code == 401

    audit_actions = [log.action for log in AuditLogRepository(db_session).list_for_user(1, limit=20)]
    assert "login_failed" in audit_actions
    assert "account_locked" in audit_actions

    metrics_body = client.get("/metrics").text
    assert 'moovesaathi_auth_total{event="login_failed",outcome="invalid_password"} 2' in metrics_body
    assert 'moovesaathi_auth_total{event="account_locked",outcome="success"} 1' in metrics_body


def test_locked_account_attempts_are_audited_and_metered(client, db_session) -> None:
    from datetime import datetime, timedelta, timezone

    from app.repositories.audit_log import AuditLogRepository
    from app.repositories.user import UserRepository

    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Locked Retry User",
            "email": "locked-retry@example.com",
            "password": "Password123",
            "phone_number": "2424242424",
        },
    )
    assert register_response.status_code == 201

    user = UserRepository(db_session).get_by_email("locked-retry@example.com")
    assert user is not None
    user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
    db_session.commit()

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "locked-retry@example.com", "password": "Password123"},
    )
    assert response.status_code == 423

    audit_actions = [log.action for log in AuditLogRepository(db_session).list_for_user(user.id, limit=20)]
    assert "login_blocked_locked" in audit_actions

    metrics_body = client.get("/metrics").text
    assert 'moovesaathi_auth_total{event="login_blocked_locked",outcome="success"} 1' in metrics_body


def test_refresh_rotates_tokens_and_logout_revokes_access(client) -> None:
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Token User",
            "email": "token@example.com",
            "password": "Password123",
            "phone_number": "7777777777",
        },
    )
    assert register_response.status_code == 201

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "token@example.com", "password": "Password123"},
    )
    assert login_response.status_code == 200
    access_token = login_response.json()["access_token"]
    refresh_token = login_response.json()["refresh_token"]

    refresh_response = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_response.status_code == 200
    rotated_access = refresh_response.json()["access_token"]
    rotated_refresh = refresh_response.json()["refresh_token"]
    assert rotated_access != access_token
    assert rotated_refresh != refresh_token

    logout_response = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {rotated_access}"},
        json={"refresh_token": rotated_refresh},
    )
    assert logout_response.status_code == 204

    me_response = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {rotated_access}"})
    assert me_response.status_code == 401

    reused_refresh = client.post("/api/v1/auth/refresh", json={"refresh_token": rotated_refresh})
    assert reused_refresh.status_code == 401


def test_change_password_revokes_existing_sessions(client) -> None:
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Password Change User",
            "email": "change@example.com",
            "password": "Password123",
            "phone_number": "5555555555",
        },
    )
    assert register_response.status_code == 201

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "change@example.com", "password": "Password123"},
    )
    assert login_response.status_code == 200
    access_token = login_response.json()["access_token"]
    refresh_token = login_response.json()["refresh_token"]

    sessions_response = client.get("/api/v1/auth/sessions", headers={"Authorization": f"Bearer {access_token}"})
    assert sessions_response.status_code == 200
    assert len(sessions_response.json()["items"]) == 1

    change_response = client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"current_password": "Password123", "new_password": "NewPassword123"},
    )
    assert change_response.status_code == 204

    me_response = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me_response.status_code == 401

    reused_refresh = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert reused_refresh.status_code == 401

    new_login = client.post(
        "/api/v1/auth/login",
        json={"email": "change@example.com", "password": "NewPassword123"},
    )
    assert new_login.status_code == 200


def test_sessions_include_device_metadata_and_refresh_preserves_it(client) -> None:
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Session Metadata User",
            "email": "metadata@example.com",
            "password": "Password123",
            "phone_number": "4444444444",
        },
    )
    assert register_response.status_code == 201

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "metadata@example.com", "password": "Password123"},
    )
    assert login_response.status_code == 200
    access_token = login_response.json()["access_token"]
    refresh_token = login_response.json()["refresh_token"]

    sessions_response = client.get("/api/v1/auth/sessions", headers={"Authorization": f"Bearer {access_token}"})
    assert sessions_response.status_code == 200
    session = sessions_response.json()["items"][0]
    assert session["current_session"] is True
    assert session["device_name"]
    assert session["user_agent"]
    assert session["ip_address"]

    refresh_response = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_response.status_code == 200

    refreshed_sessions = client.get(
        "/api/v1/auth/sessions",
        headers={"Authorization": f"Bearer {refresh_response.json()['access_token']}"},
    )
    assert refreshed_sessions.status_code == 200
    refreshed_session = refreshed_sessions.json()["items"][0]
    assert refreshed_session["current_session"] is True
    assert refreshed_session["device_name"] == session["device_name"]
    assert refreshed_session["user_agent"] == session["user_agent"]
    assert refreshed_session["ip_address"] == session["ip_address"]


def test_revoke_other_sessions_keeps_current_session(client) -> None:
    from datetime import datetime, timedelta, timezone

    from app.core.security import decode_token
    from app.services.token_store import token_store

    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Session Control User",
            "email": "control@example.com",
            "password": "Password123",
            "phone_number": "3333333333",
        },
    )
    assert register_response.status_code == 201

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "control@example.com", "password": "Password123"},
    )
    assert login_response.status_code == 200
    access_token = login_response.json()["access_token"]
    current_jti = decode_token(access_token)["session_jti"]

    token_store.register_session(
        user_id=1,
        jti="other-session-jti",
        issued_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        user_agent="Mozilla/5.0",
        ip_address="127.0.0.1",
    )

    response = client.post(
        "/api/v1/auth/sessions/revoke-others",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 204

    sessions = token_store.list_sessions(1)
    assert {session.jti for session in sessions} == {current_jti}


def test_revoke_session_is_audited(client, db_session) -> None:
    from datetime import datetime, timedelta, timezone

    from app.repositories.audit_log import AuditLogRepository
    from app.services.token_store import token_store

    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Revoke Audit User",
            "email": "revoke-audit@example.com",
            "password": "Password123",
            "phone_number": "3535353535",
        },
    )
    assert register_response.status_code == 201

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "revoke-audit@example.com", "password": "Password123"},
    )
    assert login_response.status_code == 200
    access_token = login_response.json()["access_token"]

    token_store.register_session(
        user_id=1,
        jti="revocable-session-jti",
        issued_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        user_agent="Mozilla/5.0",
        ip_address="127.0.0.1",
    )

    response = client.delete(
        "/api/v1/auth/sessions/revocable-session-jti",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 204

    audit_actions = [log.action for log in AuditLogRepository(db_session).list_for_user(1, limit=20)]
    assert "session_revoked" in audit_actions


def test_forgot_password_and_reset_password_flow(client) -> None:
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Reset User",
            "email": "reset@example.com",
            "password": "Password123",
            "phone_number": "8888888888",
        },
    )
    assert register_response.status_code == 201

    forgot_response = client.post("/api/v1/auth/forgot-password", json={"email": "reset@example.com"})
    assert forgot_response.status_code == 200
    assert "reset_token" in forgot_response.json()
    reset_token = forgot_response.json()["reset_token"]
    assert reset_token

    reset_response = client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_token, "new_password": "NewPassword123"},
    )
    assert reset_response.status_code == 204

    old_login = client.post(
        "/api/v1/auth/login",
        json={"email": "reset@example.com", "password": "Password123"},
    )
    assert old_login.status_code == 401

    new_login = client.post(
        "/api/v1/auth/login",
        json={"email": "reset@example.com", "password": "NewPassword123"},
    )
    assert new_login.status_code == 200

    reused_reset = client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_token, "new_password": "AnotherPassword123"},
    )
    assert reused_reset.status_code == 401


def test_password_reset_recovery_events_are_audited_and_metered(client, db_session) -> None:
    from app.repositories.audit_log import AuditLogRepository

    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Reset Audit User",
            "email": "reset-audit@example.com",
            "password": "Password123",
            "phone_number": "4545454545",
        },
    )
    assert register_response.status_code == 201

    forgot_response = client.post("/api/v1/auth/forgot-password", json={"email": "reset-audit@example.com"})
    assert forgot_response.status_code == 200
    reset_token = forgot_response.json()["reset_token"]

    reset_response = client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_token, "new_password": "NewPassword123"},
    )
    assert reset_response.status_code == 204

    audit_actions = [log.action for log in AuditLogRepository(db_session).list_for_user(1, limit=20)]
    assert "password_reset_requested" in audit_actions
    assert "password_reset_completed" in audit_actions

    metrics_body = client.get("/metrics").text
    assert 'moovesaathi_auth_total{event="password_reset_requested",outcome="success"} 1' in metrics_body
    assert 'moovesaathi_auth_total{event="password_reset_completed",outcome="success"} 1' in metrics_body


def test_forgot_password_is_generic_for_unknown_email(client) -> None:
    response = client.post("/api/v1/auth/forgot-password", json={"email": "unknown@example.com"})
    assert response.status_code == 200
    assert response.json()["message"] == "If an account exists for that email, a reset link has been generated."


def test_email_verification_flow_and_login_requirement(client, monkeypatch) -> None:
    monkeypatch.setattr("app.services.auth.settings.REQUIRE_EMAIL_VERIFICATION", True)

    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Verify User",
            "email": "verify@example.com",
            "password": "Password123",
            "phone_number": "1212121212",
        },
    )
    assert register_response.status_code == 201
    verification_token = register_response.json()["verification_token"]
    assert verification_token

    blocked_login = client.post(
        "/api/v1/auth/login",
        json={"email": "verify@example.com", "password": "Password123"},
    )
    assert blocked_login.status_code == 403

    verify_response = client.post("/api/v1/auth/verify-email", json={"token": verification_token})
    assert verify_response.status_code == 204

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "verify@example.com", "password": "Password123"},
    )
    assert login_response.status_code == 200


def test_resend_verification_is_generic_and_returns_token_in_non_production(client) -> None:
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Resend User",
            "email": "resend@example.com",
            "password": "Password123",
            "phone_number": "3434343434",
        },
    )
    assert register_response.status_code == 201

    resend_response = client.post(
        "/api/v1/auth/resend-verification",
        json={"email": "resend@example.com"},
    )
    assert resend_response.status_code == 200
    assert resend_response.json()["message"] == "If an account exists for that email, a verification email has been sent."
    assert resend_response.json()["verification_token"]

    unknown_response = client.post(
        "/api/v1/auth/resend-verification",
        json={"email": "unknown@example.com"},
    )
    assert unknown_response.status_code == 200
    assert unknown_response.json()["message"] == "If an account exists for that email, a verification email has been sent."


def test_login_rate_limit(client, rate_limit_settings) -> None:
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Rate Limit User",
            "email": "ratelimit@example.com",
            "password": "Password123",
            "phone_number": "1231231234",
        },
    )
    assert register_response.status_code == 201

    assert client.post(
        "/api/v1/auth/login",
        json={"email": "ratelimit@example.com", "password": "wrongpass"},
    ).status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "ratelimit@example.com", "password": "wrongpass"},
    ).status_code == 401

    blocked = client.post(
        "/api/v1/auth/login",
        json={"email": "ratelimit@example.com", "password": "wrongpass"},
    )
    assert blocked.status_code == 429


def test_login_lockout_after_repeated_failures(client, monkeypatch) -> None:
    monkeypatch.setattr("app.services.auth.settings.AUTH_MAX_FAILED_LOGIN_ATTEMPTS", 2)
    monkeypatch.setattr("app.services.auth.settings.AUTH_LOCKOUT_WINDOW_MINUTES", 15)

    assert client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Lockout User",
            "email": "lockout@example.com",
            "password": "Password123",
            "phone_number": "1231231234",
        },
    ).status_code == 201

    assert client.post(
        "/api/v1/auth/login",
        json={"email": "lockout@example.com", "password": "wrongpass"},
    ).status_code == 401

    blocked = client.post(
        "/api/v1/auth/login",
        json={"email": "lockout@example.com", "password": "wrongpass"},
    )
    assert blocked.status_code == 401

    locked = client.post(
        "/api/v1/auth/login",
        json={"email": "lockout@example.com", "password": "Password123"},
    )
    assert locked.status_code == 423
    assert locked.json()["detail"] == "Account temporarily locked due to too many failed login attempts"


def test_forgot_password_rate_limit(client, rate_limit_settings) -> None:
    assert client.post("/api/v1/auth/forgot-password", json={"email": "unknown@example.com"}).status_code == 200
    assert client.post("/api/v1/auth/forgot-password", json={"email": "unknown@example.com"}).status_code == 200

    blocked = client.post("/api/v1/auth/forgot-password", json={"email": "unknown@example.com"})
    assert blocked.status_code == 429


def test_resend_verification_rate_limit(client, rate_limit_settings) -> None:
    assert client.post("/api/v1/auth/resend-verification", json={"email": "unknown@example.com"}).status_code == 200
    assert client.post("/api/v1/auth/resend-verification", json={"email": "unknown@example.com"}).status_code == 200

    blocked = client.post("/api/v1/auth/resend-verification", json={"email": "unknown@example.com"})
    assert blocked.status_code == 429


def test_tampered_issuer_token_is_rejected(client) -> None:
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Issuer User",
            "email": "issuer@example.com",
            "password": "Password123",
            "phone_number": "5656565656",
        },
    )
    assert register_response.status_code == 201

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "issuer@example.com", "password": "Password123"},
    )
    assert login_response.status_code == 200

    token = login_response.json()["access_token"]

    from jose import jwt
    from app.core.config import settings
    from app.core.security import decode_token

    payload = decode_token(token)
    payload["iss"] = "unexpected-issuer"
    tampered = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    me_response = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {tampered}"})
    assert me_response.status_code == 401
