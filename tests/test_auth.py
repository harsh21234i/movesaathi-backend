def test_health_check(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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


def test_forgot_password_is_generic_for_unknown_email(client) -> None:
    response = client.post("/api/v1/auth/forgot-password", json={"email": "unknown@example.com"})
    assert response.status_code == 200
    assert response.json()["message"] == "If an account exists for that email, a reset link has been generated."


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


def test_forgot_password_rate_limit(client, rate_limit_settings) -> None:
    assert client.post("/api/v1/auth/forgot-password", json={"email": "unknown@example.com"}).status_code == 200
    assert client.post("/api/v1/auth/forgot-password", json={"email": "unknown@example.com"}).status_code == 200

    blocked = client.post("/api/v1/auth/forgot-password", json={"email": "unknown@example.com"})
    assert blocked.status_code == 429
