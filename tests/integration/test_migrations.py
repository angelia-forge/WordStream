from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from alembic import command
from alembic.config import Config
from app.config import get_settings


def test_alembic_upgrades_empty_database_to_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "migration-smoke.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("AUTH_MODE", "disabled")
    get_settings.cache_clear()

    command.upgrade(Config("alembic.ini"), "head")

    engine = create_engine(database_url)
    try:
        setting_columns = {
            column["name"] for column in inspect(engine).get_columns("app_settings")
        }
        entry_columns = {
            column["name"] for column in inspect(engine).get_columns("entries")
        }
        table_names = set(inspect(engine).get_table_names())
        with engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
    finally:
        engine.dispose()
        get_settings.cache_clear()

    assert database_path.exists()
    assert "default_interval" in setting_columns
    assert "default_interval_seconds" not in setting_columns
    assert {
        "vocabularies",
        "entries",
        "study_plans",
        "review_states",
        "learning_events",
    }.issubset(table_names)
    assert {"normalized_term", "entry_type", "tags"}.issubset(entry_columns)
    assert revision == "20261012_0004"
