from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models.learning import (
    LearningEvent,
    ReviewState,
    SessionAttempt,
    StudySession,
)


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
    action: str,
    *,
    attempt_id: str | None = None,
) -> dict[str, str]:
    return {
        "session_item_id": item_id,
        "attempt_id": attempt_id or str(uuid4()),
        "action": action,
        "occurred_at": datetime.now(UTC).isoformat(),
    }


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


def test_batch_reorders_retry_persists_progress_and_is_idempotent(
    client: TestClient,
) -> None:
    vocabulary_id = import_vocabulary(client)
    configure_plan(client, vocabulary_id)
    created = client.post(
        "/api/v1/study-sessions",
        json={"vocabulary_id": vocabulary_id, "resume_existing": True},
    ).json()
    session_id = created["session"]["id"]
    first, second, third, fourth = created["items"]
    first_again = outcome(first["id"], "again")
    batch = {
        "outcomes": [
            first_again,
            outcome(second["id"], "seen"),
            outcome(third["id"], "seen"),
            outcome(first["id"], "replayed"),
        ]
    }

    recorded = client.post(
        f"/api/v1/study-sessions/{session_id}/outcomes/batch",
        json=batch,
    )
    assert recorded.status_code == 200
    body = recorded.json()
    assert body["accepted"] == 4
    assert body["duplicates"] == 0
    assert body["session"]["current_index"] == 3
    assert [item["id"] for item in body["items"]] == [
        second["id"],
        third["id"],
        first["id"],
        fourth["id"],
    ]
    retried = body["items"][2]
    assert retried["result"] == "again"
    assert retried["attempt_count"] == 2

    duplicate = client.post(
        f"/api/v1/study-sessions/{session_id}/outcomes/batch",
        json=batch,
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["accepted"] == 0
    assert duplicate.json()["duplicates"] == 4
    assert duplicate.json()["session"]["current_index"] == 3

    fetched = client.get(f"/api/v1/study-sessions/{session_id}")
    assert fetched.status_code == 200
    assert fetched.json()["session"]["current_index"] == 3

    session_factory = client.app.state.session_factory
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(SessionAttempt)) == 4


def test_batch_is_atomic_and_rejects_reused_attempt_id(client: TestClient) -> None:
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
                outcome(first["id"], "seen", attempt_id=shared_id),
                outcome(second["id"], "seen", attempt_id=shared_id),
            ]
        },
    )
    assert invalid.status_code == 409
    assert invalid.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"

    fetched = client.get(f"/api/v1/study-sessions/{session_id}").json()
    assert fetched["session"]["current_index"] == 0
    assert fetched["items"][0]["result"] is None


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
    recorded = client.post(
        f"/api/v1/study-sessions/{session_id}/outcomes/batch",
        json={
            "outcomes": [
                outcome(first["id"], "seen"),
                outcome(second["id"], "again"),
                outcome(second["id"], "replayed"),
            ]
        },
    )
    assert recorded.status_code == 200

    finished = client.post(f"/api/v1/study-sessions/{session_id}/finish")
    repeated = client.post(f"/api/v1/study-sessions/{session_id}/finish")
    assert finished.status_code == 200
    assert repeated.status_code == 200
    assert finished.json() == repeated.json()
    assert finished.json()["completed_items"] == 2
    assert finished.json()["total_attempts"] == 3

    session_factory = client.app.state.session_factory
    with session_factory() as session:
        events = list(session.scalars(select(LearningEvent)))
        review_states = list(session.scalars(select(ReviewState)))
    assert len(events) == 2
    assert {event.result for event in events} == {"seen", "again"}
    assert len(review_states) == 2
    assert sorted(state.box_number for state in review_states) == [1, 2]
