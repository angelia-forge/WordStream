from fastapi.testclient import TestClient


def test_development_shell_is_rendered(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "WordStream" in response.text
    assert 'rel="manifest"' in response.text


def test_password_login_opens_protected_shell(
    protected_client: TestClient,
) -> None:
    login_page = protected_client.get("/")

    assert login_page.status_code == 200
    assert login_page.url.path == "/login"
    assert 'name="password"' in login_page.text

    logged_in = protected_client.post(
        "/login",
        data={"password": "correct-password"},
    )

    assert logged_in.status_code == 200
    assert logged_in.url.path == "/"
    assert 'name="csrf_token"' in logged_in.text


def test_service_worker_is_available(client: TestClient) -> None:
    response = client.get("/service-worker.js")

    assert response.status_code == 200
    assert response.headers["service-worker-allowed"] == "/"
