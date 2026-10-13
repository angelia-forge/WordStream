import logging

import pytest
from fastapi.testclient import TestClient


def test_cross_origin_requests_receive_no_cors_permission(
    protected_client: TestClient,
) -> None:
    origin = "https://untrusted.example"

    simple = protected_client.get(
        "/api/v1/settings",
        headers={"Origin": origin},
    )
    preflight = protected_client.options(
        "/api/v1/settings",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "X-CSRF-Token",
        },
    )

    assert "access-control-allow-origin" not in simple.headers
    assert "access-control-allow-origin" not in preflight.headers
    assert preflight.status_code == 405


def test_credentials_and_import_content_are_not_logged(
    protected_client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    password = "log-secret-password"
    api_key = "test-api-key"
    imported_term = "log-secret-imported-term"

    with caplog.at_level(logging.DEBUG):
        login = protected_client.post(
            "/api/v1/auth/login",
            json={"password": password},
        )
        preview = protected_client.post(
            "/api/v1/vocabularies/import/preview",
            headers={"X-API-Key": api_key},
            data={
                "name": "Sensitive import",
                "text": f"term|meaning\n{imported_term}|private",
            },
        )

    assert login.status_code == 401
    assert preview.status_code == 200
    assert password not in caplog.text
    assert api_key not in caplog.text
    assert imported_term not in caplog.text
