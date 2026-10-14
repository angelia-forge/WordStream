from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from alembic import command
from alembic.config import Config
from app.config import AuthMode, Environment, Settings, get_settings
from app.main import create_app


@pytest.fixture
def database_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[str]:
    url = f"sqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("AUTH_MODE", "disabled")
    get_settings.cache_clear()

    alembic_config = Config("alembic.ini")
    command.upgrade(alembic_config, "head")
    yield url
    get_settings.cache_clear()


@pytest.fixture
def client(database_url: str) -> Iterator[TestClient]:
    config = Settings(
        environment=Environment.TEST,
        database_url=database_url,
        auth_mode=AuthMode.DISABLED,
    )
    with TestClient(create_app(config)) as test_client:
        yield test_client


@pytest.fixture
def protected_client(database_url: str) -> Iterator[TestClient]:
    config = Settings(
        environment=Environment.TEST,
        database_url=database_url,
        auth_mode=AuthMode.PASSWORD,
        app_password="correct-password",
        secret_key="test-secret-with-enough-entropy!",
        app_api_key="test-api-key",
    )
    with TestClient(create_app(config)) as test_client:
        yield test_client
