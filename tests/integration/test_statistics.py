from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.learning import LearningEvent, ReviewState
from app.models.vocabulary import Entry


def import_vocabulary(client: TestClient, name: str, terms: list[str]) -> int:
    text = "term|meaning\n" + "\n".join(f"{term}|meaning" for term in terms)
    preview = client.post(
        "/api/v1/vocabularies/import/preview",
        data={"name": name, "text": text},
    )
    assert preview.status_code == 200
    imported = client.post(
        "/api/v1/vocabularies/import",
        data={
            "name": name,
            "text": text,
            "preview_digest": preview.json()["preview_digest"],
        },
    )
    assert imported.status_code == 201
    return int(imported.json()["vocabulary_id"])


def add_event(
    session: Any,
    entry: Entry,
    *,
    vocabulary_name: str,
    activity_date: date,
    result: str = "seen",
) -> None:
    session.add(
        LearningEvent(
            client_event_id=str(uuid4()),
            entry_id=entry.id,
            term_key=entry.normalized_term,
            term_snapshot=entry.term,
            vocabulary_snapshot={
                "id": entry.vocabulary_id,
                "name": vocabulary_name,
            },
            result=result,
            attempt_count=1,
            client_attempt_count=1,
            occurred_at=datetime.now(UTC),
            timezone="Asia/Shanghai",
            activity_date=activity_date,
        )
    )


def test_today_statistics_are_zero_without_data(client: TestClient) -> None:
    statistics = client.get("/api/v1/statistics/today")
    reviews = client.get("/api/v1/reviews/today")

    assert statistics.status_code == 200
    assert statistics.json()["learned_terms"] == 0
    assert statistics.json()["streak"] == 0
    assert statistics.json()["total_entries"] == 0
    assert statistics.json()["timezone"] == "Asia/Shanghai"
    assert reviews.status_code == 200
    assert reviews.json()["due_reviews"] == 0


def test_today_statistics_deduplicate_and_filter_by_vocabulary(
    client: TestClient,
) -> None:
    first_id = import_vocabulary(client, "First", ["alpha", "beta"])
    second_id = import_vocabulary(client, "Second", ["gamma"])
    today = date.fromisoformat(client.get("/api/v1/statistics/today").json()["date"])
    now = datetime.now(UTC)
    session_factory = client.app.state.session_factory

    with session_factory() as session:
        first_entries = list(
            session.scalars(
                select(Entry).where(Entry.vocabulary_id == first_id).order_by(Entry.id)
            )
        )
        second_entry = session.scalar(
            select(Entry).where(Entry.vocabulary_id == second_id)
        )
        assert second_entry is not None
        add_event(
            session,
            first_entries[0],
            vocabulary_name="First",
            activity_date=today,
        )
        add_event(
            session,
            first_entries[0],
            vocabulary_name="First",
            activity_date=today,
            result="again",
        )
        add_event(
            session,
            first_entries[1],
            vocabulary_name="First",
            activity_date=today,
        )
        add_event(
            session,
            first_entries[0],
            vocabulary_name="First",
            activity_date=today - timedelta(days=1),
        )
        add_event(
            session,
            second_entry,
            vocabulary_name="Second",
            activity_date=today,
        )
        session.add_all(
            [
                ReviewState(
                    entry_id=first_entries[0].id,
                    box_number=0,
                    next_review_at=now - timedelta(minutes=1),
                ),
                ReviewState(
                    entry_id=first_entries[1].id,
                    box_number=1,
                    next_review_at=now + timedelta(days=1),
                ),
                ReviewState(
                    entry_id=second_entry.id,
                    box_number=0,
                    next_review_at=now - timedelta(minutes=1),
                ),
            ]
        )
        session.commit()

    all_statistics = client.get("/api/v1/statistics/today")
    filtered_statistics = client.get(
        "/api/v1/statistics/today",
        params={"vocabulary_id": first_id},
    )
    all_reviews = client.get("/api/v1/reviews/today")
    filtered_reviews = client.get(
        "/api/v1/reviews/today",
        params={"vocabulary_id": first_id},
    )

    assert all_statistics.json()["learned_terms"] == 3
    assert all_statistics.json()["streak"] == 2
    assert all_statistics.json()["total_entries"] == 3
    assert filtered_statistics.json()["learned_terms"] == 2
    assert filtered_statistics.json()["streak"] == 2
    assert filtered_statistics.json()["total_entries"] == 2
    assert all_reviews.json()["due_reviews"] == 2
    assert filtered_reviews.json()["due_reviews"] == 1


def test_deleted_vocabulary_keeps_history_but_not_live_counts(
    client: TestClient,
) -> None:
    vocabulary_id = import_vocabulary(client, "Deleted", ["history"])
    today = date.fromisoformat(client.get("/api/v1/statistics/today").json()["date"])
    session_factory = client.app.state.session_factory
    with session_factory() as session:
        entry = session.scalar(
            select(Entry).where(Entry.vocabulary_id == vocabulary_id)
        )
        assert entry is not None
        add_event(
            session,
            entry,
            vocabulary_name="Deleted",
            activity_date=today,
        )
        session.add(
            ReviewState(
                entry_id=entry.id,
                box_number=0,
                next_review_at=datetime.now(UTC) - timedelta(minutes=1),
            )
        )
        session.commit()

    deleted = client.delete(
        f"/api/v1/vocabularies/{vocabulary_id}",
        params={"confirm_id": vocabulary_id},
    )
    assert deleted.status_code == 204

    statistics = client.get(
        "/api/v1/statistics/today",
        params={"vocabulary_id": vocabulary_id},
    )
    reviews = client.get(
        "/api/v1/reviews/today",
        params={"vocabulary_id": vocabulary_id},
    )
    assert statistics.status_code == 200
    assert statistics.json()["learned_terms"] == 1
    assert statistics.json()["streak"] == 1
    assert statistics.json()["total_entries"] == 0
    assert reviews.status_code == 200
    assert reviews.json()["due_reviews"] == 0


def test_vocabulary_filter_must_be_positive(client: TestClient) -> None:
    assert (
        client.get(
            "/api/v1/statistics/today",
            params={"vocabulary_id": 0},
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/v1/reviews/today",
            params={"vocabulary_id": -1},
        ).status_code
        == 422
    )
