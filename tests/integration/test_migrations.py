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
        event_columns = {
            column["name"] for column in inspect(engine).get_columns("learning_events")
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
        "study_sessions",
        "session_items",
        "session_attempts",
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
    assert {
        "session_item_id",
        "client_event_id",
        "client_attempt_count",
        "vocabulary_snapshot",
    }.issubset(event_columns)
    assert revision == "20261013_0007"


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


def test_leitner_migration_preserves_existing_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "leitner-data.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("AUTH_MODE", "disabled")
    get_settings.cache_clear()
    config = Config("alembic.ini")
    command.upgrade(config, "20261013_0006")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO vocabularies "
                "(id, name, source_filename, entry_count, created_at) "
                "VALUES (1, 'Existing', NULL, 1, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO entries "
                "(id, vocabulary_id, term, normalized_term, entry_type, meaning, "
                "part_of_speech, phonetic, example, tags, created_at) "
                "VALUES (1, 1, 'Term', 'term', 'word', 'Meaning', NULL, NULL, "
                "NULL, '[]', CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO review_states "
                "(id, entry_id, box_number, next_review_at, last_reviewed_at) "
                "VALUES (1, 1, 3, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO learning_events "
                "(id, session_item_id, entry_id, term_key, term_snapshot, "
                "vocabulary_id_snapshot, vocabulary_name_snapshot, result, "
                "attempts, occurred_at, received_at, timezone, activity_date) "
                "VALUES (1, NULL, 1, 'term', 'Term', 1, 'Existing', "
                "'remembered', 2, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, "
                "'UTC', CURRENT_DATE)"
            )
        )
    engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            box_number = connection.execute(
                text("SELECT box_number FROM review_states WHERE id = 1")
            ).scalar_one()
            event = connection.execute(
                text(
                    "SELECT result, attempt_count, client_attempt_count, "
                    "json_extract(vocabulary_snapshot, '$.name'), "
                    "length(client_event_id) "
                    "FROM learning_events WHERE id = 1"
                )
            ).one()
    finally:
        engine.dispose()

    assert box_number == 2
    assert tuple(event) == ("seen", 2, 2, "Existing", 36)

    command.downgrade(config, "20261013_0006")
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            restored_box = connection.execute(
                text("SELECT box_number FROM review_states WHERE id = 1")
            ).scalar_one()
            restored_event = connection.execute(
                text(
                    "SELECT result, attempts, vocabulary_id_snapshot, "
                    "vocabulary_name_snapshot "
                    "FROM learning_events WHERE id = 1"
                )
            ).one()
    finally:
        engine.dispose()
        get_settings.cache_clear()

    assert restored_box == 3
    assert tuple(restored_event) == ("seen", 2, 1, "Existing")
