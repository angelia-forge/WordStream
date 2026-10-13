from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select

from app.models.learning import (
    LearningEvent,
    ReviewState,
    SessionAttempt,
    StudySession,
)
from app.repositories.study_sessions import StudySessionRepository


def import_vocabulary(client: TestClient, *, count: int = 4) -> int:
    rows = ["term|meaning|pos|phonetic|example"]
    rows.extend(
        f"term-{index}|meaning-{index}|noun|/{index}/|example-{index}"
        for index in range(count)
    )
    preview = client.post(
        "/api/v1/vocabularies/import/preview",
        data={"name": "Session words", "text": "\n".join(rows)},
    )
    assert preview.status_code == 200
    imported = client.post(
        "/api/v1/vocabularies/import",
        data={
            "name": "Session words",
            "text": "\n".join(rows),
            "preview_digest": preview.json()["preview_digest"],
        },
    )
    assert imported.status_code == 201
    return int(imported.json()["vocabulary_id"])


def configure_plan(client: TestClient, vocabulary_id: int, **changes: Any) -> None:
    payload = {
        "daily_new_count": 10,
        "daily_review_count": 10,
        "interval_seconds": 2,
        "is_random": False,
        "is_loop": False,
        **changes,
    }
    response = client.put(
        f"/api/v1/vocabularies/{vocabulary_id}/plan",
        json=payload,
    )
    assert response.status_code == 200


def outcome(
    item_id: str,
    result: str,
    *,
    client_event_id: str | None = None,
    occurred_at: datetime | None = None,
    attempt_count: int = 1,
) -> dict[str, str | int]:
    return {
        "session_item_id": item_id,
        "client_event_id": client_event_id or str(uuid4()),
        "result": result,
        "attempt_count": attempt_count,
        "occurred_at": (occurred_at or datetime.now(UTC)).isoformat(),
    }


def test_session_endpoints_reject_invalid_or_missing_resources(
    client: TestClient,
) -> None:
    invalid_create = client.post(
        "/api/v1/study-sessions",
        json={"vocabulary_id": 0},
    )
    assert invalid_create.status_code == 422

    missing_session_id = 999_999
    missing_get = client.get(f"/api/v1/study-sessions/{missing_session_id}")
    missing_batch = client.post(
        f"/api/v1/study-sessions/{missing_session_id}/outcomes/batch",
        json={"outcomes": [outcome(str(uuid4()), "seen")]},
    )
    missing_finish = client.post(f"/api/v1/study-sessions/{missing_session_id}/finish")

    for response in (missing_get, missing_batch, missing_finish):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_create_requires_plan_and_non_empty_queue(client: TestClient) -> None:
    vocabulary_id = import_vocabulary(client)

    missing_plan = client.post(
        "/api/v1/study-sessions",
        json={"vocabulary_id": vocabulary_id, "resume_existing": True},
    )
    assert missing_plan.status_code == 409
    assert missing_plan.json()["error"]["code"] == "PLAN_REQUIRED"

    configure_plan(
        client,
        vocabulary_id,
        daily_new_count=0,
        daily_review_count=0,
    )
    empty = client.post(
        "/api/v1/study-sessions",
        json={"vocabulary_id": vocabulary_id, "resume_existing": True},
    )
    assert empty.status_code == 409
    assert empty.json()["error"]["code"] == "EMPTY_STUDY_QUEUE"


def test_create_returns_snapshots_resumes_and_can_replace_active(
    client: TestClient,
) -> None:
    vocabulary_id = import_vocabulary(client)
    configure_plan(client, vocabulary_id)

    created = client.post(
        "/api/v1/study-sessions",
        json={"vocabulary_id": vocabulary_id, "resume_existing": True},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["session"]["status"] == "active"
    assert body["session"]["plan_snapshot"]["interval_seconds"] == 2
    assert [item["entry"]["term"] for item in body["items"]] == [
        "term-0",
        "term-1",
        "term-2",
        "term-3",
    ]
    assert body["items"][0]["entry"]["part_of_speech"] == "noun"

    resumed = client.post(
        "/api/v1/study-sessions",
        json={"vocabulary_id": vocabulary_id, "resume_existing": True},
    )
    assert resumed.status_code == 201
    assert resumed.json()["session"]["id"] == body["session"]["id"]

    replaced = client.post(
        "/api/v1/study-sessions",
        json={"vocabulary_id": vocabulary_id, "resume_existing": False},
    )
    assert replaced.status_code == 201
    assert replaced.json()["session"]["id"] != body["session"]["id"]

    session_factory = client.app.state.session_factory
    with session_factory() as session:
        old_session = session.get(StudySession, body["session"]["id"])
        assert old_session is not None
        assert old_session.status == "abandoned"
        assert old_session.finished_at is not None


def test_batch_persists_progress_and_is_idempotent(
    client: TestClient,
) -> None:
    vocabulary_id = import_vocabulary(client)
    configure_plan(client, vocabulary_id)
    created = client.post(
        "/api/v1/study-sessions",
        json={"vocabulary_id": vocabulary_id, "resume_existing": True},
    ).json()
    session_id = created["session"]["id"]
    first, second, third = created["items"][:3]
    first_again = outcome(first["id"], "again")
    batch = {
        "outcomes": [
            first_again,
            outcome(second["id"], "seen"),
            outcome(third["id"], "seen"),
        ]
    }

    recorded = client.post(
        f"/api/v1/study-sessions/{session_id}/outcomes/batch",
        json=batch,
    )
    assert recorded.status_code == 200
    body = recorded.json()
    assert body["accepted"] == 3
    assert body["duplicates"] == 0
    assert body["session"]["current_index"] == 3
    assert body["items"][0]["result"] == "again"
    assert body["items"][0]["attempt_count"] == 1

    duplicate = client.post(
        f"/api/v1/study-sessions/{session_id}/outcomes/batch",
        json=batch,
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["accepted"] == 0
    assert duplicate.json()["duplicates"] == 3
    assert duplicate.json()["session"]["current_index"] == 3

    fetched = client.get(f"/api/v1/study-sessions/{session_id}")
    assert fetched.status_code == 200
    assert fetched.json()["session"]["current_index"] == 3

    session_factory = client.app.state.session_factory
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(SessionAttempt)) == 3
        assert session.scalar(select(func.count()).select_from(LearningEvent)) == 3


def test_new_events_capture_the_current_database_timezone(
    client: TestClient,
) -> None:
    vocabulary_id = import_vocabulary(client, count=2)
    configure_plan(client, vocabulary_id)
    created = client.post(
        "/api/v1/study-sessions",
        json={"vocabulary_id": vocabulary_id},
    ).json()
    session_id = created["session"]["id"]
    first, second = created["items"]

    assert (
        client.patch(
            "/api/v1/settings",
            json={"timezone": "UTC"},
        ).status_code
        == 200
    )
    first_time = datetime.now(UTC)
    first_response = client.post(
        f"/api/v1/study-sessions/{session_id}/outcomes/batch",
        json={"outcomes": [outcome(first["id"], "seen", occurred_at=first_time)]},
    )
    assert first_response.status_code == 200

    assert (
        client.patch(
            "/api/v1/settings",
            json={"timezone": "America/New_York"},
        ).status_code
        == 200
    )
    second_time = datetime.now(UTC)
    second_response = client.post(
        f"/api/v1/study-sessions/{session_id}/outcomes/batch",
        json={"outcomes": [outcome(second["id"], "again", occurred_at=second_time)]},
    )
    assert second_response.status_code == 200

    session_factory = client.app.state.session_factory
    with session_factory() as session:
        events = list(session.scalars(select(LearningEvent).order_by(LearningEvent.id)))
        assert [event.timezone for event in events] == [
            "UTC",
            "America/New_York",
        ]
        assert events[0].activity_date == first_time.date()
        assert (
            events[1].activity_date
            == second_time.astimezone(ZoneInfo("America/New_York")).date()
        )


def test_batch_is_atomic_and_rejects_reused_client_event_id(
    client: TestClient,
) -> None:
    vocabulary_id = import_vocabulary(client)
    configure_plan(client, vocabulary_id)
    created = client.post(
        "/api/v1/study-sessions",
        json={"vocabulary_id": vocabulary_id, "resume_existing": True},
    ).json()
    session_id = created["session"]["id"]
    first, second = created["items"][:2]
    shared_id = str(uuid4())

    invalid = client.post(
        f"/api/v1/study-sessions/{session_id}/outcomes/batch",
        json={
            "outcomes": [
                outcome(first["id"], "seen", client_event_id=shared_id),
                outcome(second["id"], "seen", client_event_id=shared_id),
            ]
        },
    )
    assert invalid.status_code == 409
    assert invalid.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"

    fetched = client.get(f"/api/v1/study-sessions/{session_id}").json()
    assert fetched["session"]["current_index"] == 0
    assert fetched["items"][0]["result"] is None


def test_batch_rejects_out_of_window_timestamp(client: TestClient) -> None:
    vocabulary_id = import_vocabulary(client, count=1)
    configure_plan(client, vocabulary_id)
    created = client.post(
        "/api/v1/study-sessions",
        json={"vocabulary_id": vocabulary_id},
    ).json()

    response = client.post(
        f"/api/v1/study-sessions/{created['session']['id']}/outcomes/batch",
        json={
            "outcomes": [
                outcome(
                    created["items"][0]["id"],
                    "seen",
                    occurred_at=datetime.now(UTC) - timedelta(hours=25),
                )
            ]
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_item_conflict_rolls_back_the_entire_batch(client: TestClient) -> None:
    vocabulary_id = import_vocabulary(client, count=2)
    configure_plan(client, vocabulary_id)
    created = client.post(
        "/api/v1/study-sessions",
        json={"vocabulary_id": vocabulary_id},
    ).json()
    session_id = created["session"]["id"]
    first, second = created["items"]
    initial = client.post(
        f"/api/v1/study-sessions/{session_id}/outcomes/batch",
        json={"outcomes": [outcome(second["id"], "seen")]},
    )
    assert initial.status_code == 200

    conflicted = client.post(
        f"/api/v1/study-sessions/{session_id}/outcomes/batch",
        json={
            "outcomes": [
                outcome(first["id"], "seen"),
                outcome(second["id"], "again"),
            ]
        },
    )
    assert conflicted.status_code == 409
    assert conflicted.json()["error"]["code"] == "OUTCOME_ALREADY_RECORDED"

    session_factory = client.app.state.session_factory
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(LearningEvent)) == 1
        refreshed = session.get(StudySession, session_id)
        assert refreshed is not None
        assert refreshed.current_index == 1
        first_item = next(item for item in refreshed.items if item.id == first["id"])
        assert first_item.result is None


def test_client_event_id_conflict_does_not_change_original_event(
    client: TestClient,
) -> None:
    vocabulary_id = import_vocabulary(client, count=1)
    configure_plan(client, vocabulary_id)
    created = client.post(
        "/api/v1/study-sessions",
        json={"vocabulary_id": vocabulary_id},
    ).json()
    item = created["items"][0]
    client_event_id = str(uuid4())
    occurred_at = datetime.now(UTC)
    original = outcome(
        item["id"],
        "seen",
        client_event_id=client_event_id,
        occurred_at=occurred_at,
    )
    assert (
        client.post(
            f"/api/v1/study-sessions/{created['session']['id']}/outcomes/batch",
            json={"outcomes": [original]},
        ).status_code
        == 200
    )

    changed = {**original, "result": "again"}
    response = client.post(
        f"/api/v1/study-sessions/{created['session']['id']}/outcomes/batch",
        json={"outcomes": [changed]},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_concurrent_outcomes_for_one_item_have_one_winner(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vocabulary_id = import_vocabulary(client, count=1)
    configure_plan(client, vocabulary_id)
    created = client.post(
        "/api/v1/study-sessions",
        json={"vocabulary_id": vocabulary_id},
    ).json()
    session_id = created["session"]["id"]
    item_id = created["items"][0]["id"]
    flush_barrier = Barrier(2)
    original_flush = StudySessionRepository.flush

    def synchronized_flush(repository: StudySessionRepository) -> None:
        flush_barrier.wait(timeout=5)
        original_flush(repository)

    monkeypatch.setattr(StudySessionRepository, "flush", synchronized_flush)
    payloads = [
        {"outcomes": [outcome(item_id, "seen")]},
        {"outcomes": [outcome(item_id, "again")]},
    ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(
                lambda payload: client.post(
                    f"/api/v1/study-sessions/{session_id}/outcomes/batch",
                    json=payload,
                ),
                payloads,
            )
        )

    assert sorted(response.status_code for response in responses) == [200, 409]
    conflict = next(response for response in responses if response.status_code == 409)
    assert conflict.json()["error"]["code"] == "OUTCOME_ALREADY_RECORDED"
    session_factory = client.app.state.session_factory
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(LearningEvent)) == 1


def test_sqlite_write_lock_returns_database_busy(client: TestClient) -> None:
    vocabulary_id = import_vocabulary(client, count=1)
    configure_plan(client, vocabulary_id)
    created = client.post(
        "/api/v1/study-sessions",
        json={"vocabulary_id": vocabulary_id},
    ).json()
    session_id = created["session"]["id"]
    item_id = created["items"][0]["id"]
    engine = client.app.state.engine

    def set_short_timeout(
        dbapi_connection: Any,
        connection_record: Any,
        connection_proxy: Any,
    ) -> None:
        del connection_record, connection_proxy
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA busy_timeout=1")
        cursor.close()

    with engine.connect() as locking_connection:
        locking_connection.exec_driver_sql("BEGIN IMMEDIATE")
        event.listen(engine, "checkout", set_short_timeout)
        try:
            response = client.post(
                f"/api/v1/study-sessions/{session_id}/outcomes/batch",
                json={"outcomes": [outcome(item_id, "seen")]},
            )
        finally:
            event.remove(engine, "checkout", set_short_timeout)
            locking_connection.rollback()

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATABASE_BUSY"


def test_finish_is_idempotent_and_updates_history_and_review_state(
    client: TestClient,
) -> None:
    vocabulary_id = import_vocabulary(client, count=2)
    configure_plan(client, vocabulary_id)
    created = client.post(
        "/api/v1/study-sessions",
        json={"vocabulary_id": vocabulary_id, "resume_existing": True},
    ).json()
    session_id = created["session"]["id"]
    first, second = created["items"]
    batch = {
        "outcomes": [
            outcome(first["id"], "seen"),
            outcome(second["id"], "again"),
        ]
    }
    recorded = client.post(
        f"/api/v1/study-sessions/{session_id}/outcomes/batch",
        json=batch,
    )
    assert recorded.status_code == 200

    finished = client.post(f"/api/v1/study-sessions/{session_id}/finish")
    repeated = client.post(f"/api/v1/study-sessions/{session_id}/finish")
    assert finished.status_code == 200
    assert repeated.status_code == 200
    assert finished.json() == repeated.json()
    assert finished.json()["completed_items"] == 2
    assert finished.json()["total_attempts"] == 2
    duplicate = client.post(
        f"/api/v1/study-sessions/{session_id}/outcomes/batch",
        json=batch,
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicates"] == 2

    session_factory = client.app.state.session_factory
    with session_factory() as session:
        events = list(session.scalars(select(LearningEvent)))
        review_states = list(session.scalars(select(ReviewState)))
    assert len(events) == 2
    assert {event.result for event in events} == {"seen", "again"}
    assert len(review_states) == 2
    assert sorted(state.box_number for state in review_states) == [0, 0]
