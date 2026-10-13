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
        plan_columns = {
            column["name"] for column in inspect(engine).get_columns("study_plans")
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
    assert {
        "daily_new_count",
        "daily_review_count",
        "interval_seconds",
        "is_random",
        "is_loop",
        "updated_at",
    }.issubset(plan_columns)
    assert "daily_new_limit" not in plan_columns
    assert revision == "20261013_0005"


def test_study_plan_migration_preserves_existing_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "migration-data.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("AUTH_MODE", "disabled")
    get_settings.cache_clear()

    config = Config("alembic.ini")
    command.upgrade(config, "20261012_0004")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO vocabularies "
                "(id, name, source_filename, entry_count, created_at) "
                "VALUES (1, 'Existing', NULL, 0, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO study_plans "
                "(id, vocabulary_id, daily_new_limit, created_at) "
                "VALUES (1, 1, 17, CURRENT_TIMESTAMP)"
            )
        )
    engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT daily_new_count, daily_review_count, "
                    "interval_seconds, is_random, is_loop "
                    "FROM study_plans WHERE id = 1"
                )
            ).one()
    finally:
        engine.dispose()
        get_settings.cache_clear()

    assert tuple(row) == (17, 20, 5, 0, 0)
