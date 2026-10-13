from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models.learning import ReviewState, StudyPlan
from app.models.vocabulary import Entry
from app.services.study_plans import StudyPlanService
from app.unit_of_work import SqlAlchemyUnitOfWork


def import_vocabulary(client: TestClient) -> int:
    text = (
        "term|meaning\n"
        "due|due\n"
        "future|future\n"
        "unscheduled|unscheduled\n"
        "new-entry|new"
    )
    preview = client.post(
        "/api/v1/vocabularies/import/preview",
        data={"name": "Study queue", "text": text},
    )
    assert preview.status_code == 200
    response = client.post(
        "/api/v1/vocabularies/import",
        data={
            "name": "Study queue",
            "text": text,
            "preview_digest": preview.json()["preview_digest"],
        },
    )
    assert response.status_code == 201
    return int(response.json()["vocabulary_id"])


def plan_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "daily_new_count": 12,
        "daily_review_count": 8,
        "interval_seconds": 4,
        "is_random": False,
        "is_loop": True,
    }
    payload.update(overrides)
    return payload


def test_put_creates_updates_and_gets_one_plan(client: TestClient) -> None:
    vocabulary_id = import_vocabulary(client)
    endpoint = f"/api/v1/vocabularies/{vocabulary_id}/plan"

    missing = client.get(endpoint)
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "PLAN_NOT_FOUND"

    created = client.put(endpoint, json=plan_payload())
    assert created.status_code == 200
    created_body = created.json()
    assert created_body["daily_new_count"] == 12
    assert created_body["daily_review_count"] == 8
    assert created_body["interval_seconds"] == 4
    assert created_body["is_loop"] is True

    updated = client.put(
        endpoint,
        json=plan_payload(
            daily_new_count=0,
            daily_review_count=30,
            interval_seconds=10,
            is_random=True,
            is_loop=False,
        ),
    )
    assert updated.status_code == 200
    updated_body = updated.json()
    assert updated_body["id"] == created_body["id"]
    assert updated_body["created_at"] == created_body["created_at"]
    assert updated_body["daily_new_count"] == 0
    assert updated_body["daily_review_count"] == 30
    assert updated_body["is_random"] is True

    fetched = client.get(endpoint)
    assert fetched.status_code == 200
    assert fetched.json() == updated_body

    session_factory = client.app.state.session_factory
    with session_factory() as session:
        count = session.scalar(select(func.count()).select_from(StudyPlan))
    assert count == 1


def test_plan_validation_and_missing_vocabulary(client: TestClient) -> None:
    vocabulary_id = import_vocabulary(client)
    endpoint = f"/api/v1/vocabularies/{vocabulary_id}/plan"

    assert (
        client.put(
            endpoint,
            json=plan_payload(interval_seconds=0),
        ).status_code
        == 422
    )
    assert (
        client.put(
            endpoint,
            json=plan_payload(interval_seconds=11),
        ).status_code
        == 422
    )
    assert (
        client.put(
            endpoint,
            json=plan_payload(daily_review_count=-1),
        ).status_code
        == 422
    )

    missing = client.put(
        "/api/v1/vocabularies/999999/plan",
        json=plan_payload(),
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_queue_selects_due_reviews_and_entries_without_state(
    client: TestClient,
) -> None:
    vocabulary_id = import_vocabulary(client)
    response = client.put(
        f"/api/v1/vocabularies/{vocabulary_id}/plan",
        json=plan_payload(),
    )
    assert response.status_code == 200
    now = datetime.now(UTC)
    session_factory = client.app.state.session_factory

    with session_factory() as session:
        entries = {
            item.term: item
            for item in session.scalars(
                select(Entry).where(Entry.vocabulary_id == vocabulary_id)
            )
        }
        session.add_all(
            [
                ReviewState(
                    entry_id=entries["due"].id,
                    next_review_at=now - timedelta(days=1),
                ),
                ReviewState(
                    entry_id=entries["future"].id,
                    next_review_at=now + timedelta(days=1),
                ),
                ReviewState(
                    entry_id=entries["unscheduled"].id,
                    next_review_at=None,
                ),
            ]
        )
        session.commit()

    queue = StudyPlanService(SqlAlchemyUnitOfWork(session_factory)).build_queue(
        vocabulary_id, now=now
    )

    assert [(item.term, item.kind) for item in queue.items] == [
        ("due", "review"),
        ("new-entry", "new"),
    ]
    assert queue.interval_seconds == 4
    assert queue.is_loop is True
