def test_http_exception_response_includes_code_and_request_id(client) -> None:
    response = client.get("/api/v1/rides/99999", headers={"Authorization": "Bearer invalid-token", "x-request-id": "req-123"})

    assert response.status_code == 401
    body = response.json()
    assert body["detail"] == "Could not validate credentials"
    assert body["code"] == "unauthorized"
    assert body["request_id"] == "req-123"


def test_validation_error_response_has_standard_shape(client) -> None:
    response = client.post(
        "/api/v1/auth/register",
        headers={"x-request-id": "req-456"},
        json={
            "full_name": "A",
            "email": "not-an-email",
            "password": "weak",
            "role": "driver",
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["detail"] == "Request validation failed"
    assert body["code"] == "validation_error"
    assert body["request_id"] == "req-456"
    assert isinstance(body["errors"], list)
