from fastapi.testclient import TestClient


def test_protected_endpoint_requires_authentication(
    protected_client: TestClient,
) -> None:
    response = protected_client.get("/api/v1/settings")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_password_session_and_csrf(protected_client: TestClient) -> None:
    login = protected_client.post(
        "/api/v1/auth/login",
        json={"password": "correct-password"},
    )

    assert login.status_code == 200
    csrf_token = login.json()["csrf_token"]
    assert protected_client.get("/api/v1/auth/session").status_code == 200

    rejected = protected_client.patch(
        "/api/v1/settings",
        json={"tts_rate": 1.1},
    )
    assert rejected.status_code == 403
    assert rejected.json()["error"]["code"] == "CSRF_FAILED"

    accepted = protected_client.patch(
        "/api/v1/settings",
        headers={"X-CSRF-Token": csrf_token},
        json={"tts_rate": 1.1},
    )
    assert accepted.status_code == 200

    logout = protected_client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert logout.status_code == 204
    assert protected_client.get("/api/v1/auth/session").status_code == 401


def test_api_key_bypasses_cookie_csrf(protected_client: TestClient) -> None:
    headers = {"X-API-Key": "test-api-key"}

    response = protected_client.patch(
        "/api/v1/settings",
        headers=headers,
        json={"daily_goal": 12},
    )

    assert response.status_code == 200
    assert response.json()["daily_goal"] == 12


def test_failed_logins_are_rate_limited(protected_client: TestClient) -> None:
    for _ in range(5):
        response = protected_client.post(
            "/api/v1/auth/login",
            json={"password": "wrong"},
        )
        assert response.status_code == 401

    limited = protected_client.post(
        "/api/v1/auth/login",
        json={"password": "wrong"},
    )
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "RATE_LIMITED"
