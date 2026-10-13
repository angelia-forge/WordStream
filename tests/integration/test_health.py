from uuid import UUID

from fastapi.testclient import TestClient


def test_health_reports_database_and_migration(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "application": "WordStream",
        "version": "0.1.0",
        "database": "ok",
        "migration": "current",
        "revision": "20261013_0006",
    }
    UUID(response.headers["X-Request-ID"])


def test_valid_request_id_is_preserved(client: TestClient) -> None:
    request_id = "975a9cd9-4467-40f8-94e4-5c0ea0a9a580"

    response = client.get("/api/v1/health", headers={"X-Request-ID": request_id})

    assert response.headers["X-Request-ID"] == request_id


def test_invalid_request_id_is_replaced(client: TestClient) -> None:
    response = client.get(
        "/api/v1/health",
        headers={"X-Request-ID": "not-a-uuid"},
    )

    generated = response.headers["X-Request-ID"]
    UUID(generated)
    assert generated != "not-a-uuid"


def test_non_v4_request_id_is_replaced(client: TestClient) -> None:
    request_id = "0d8f6e40-a6f3-11f0-8000-000000000001"

    response = client.get(
        "/api/v1/health",
        headers={"X-Request-ID": request_id},
    )

    generated = UUID(response.headers["X-Request-ID"])
    assert generated.version == 4
