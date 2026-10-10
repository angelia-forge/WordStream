from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models.setting import AppSetting


def test_settings_are_bootstrapped_once(client: TestClient) -> None:
    first = client.get("/api/v1/settings")
    second = client.get("/api/v1/settings")

    assert first.status_code == 200
    assert first.json()["timezone"] == "Asia/Shanghai"
    assert second.status_code == 200

    session_factory = client.app.state.session_factory
    with session_factory() as session:
        count = session.scalar(select(func.count()).select_from(AppSetting))
    assert count == 1


def test_settings_can_be_updated(client: TestClient) -> None:
    response = client.patch(
        "/api/v1/settings",
        json={
            "timezone": "Europe/London",
            "tts_rate": 1.25,
            "default_interval_seconds": 8,
            "daily_goal": 30,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["timezone"] == "Europe/London"
    assert body["tts_rate"] == 1.25
    assert body["default_interval_seconds"] == 8
    assert body["daily_goal"] == 30


def test_invalid_timezone_has_structured_error(client: TestClient) -> None:
    response = client.patch(
        "/api/v1/settings",
        json={"timezone": "Mars/Olympus"},
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["request_id"] == response.headers["X-Request-ID"]
