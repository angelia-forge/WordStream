from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models.learning import LearningEvent, ReviewState, StudyPlan
from app.models.vocabulary import Entry


def preview_text(
    client: TestClient,
    text: str,
    *,
    name: str = "Test vocabulary",
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/vocabularies/import/preview",
        data={"name": name, "text": text, "duplicate_policy": "skip"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def commit_text(
    client: TestClient,
    text: str,
    preview: dict[str, Any],
    *,
    name: str = "Test vocabulary",
) -> Any:
    return client.post(
        "/api/v1/vocabularies/import",
        data={
            "name": name,
            "text": text,
            "duplicate_policy": "skip",
            "preview_digest": preview["preview_digest"],
        },
    )


def test_pasted_phrase_import_succeeds(client: TestClient) -> None:
    text = "term | meaning | type\nin order to | 为了 | phrase"
    preview = preview_text(client, text)

    response = commit_text(client, text, preview)

    assert response.status_code == 201
    vocabulary_id = response.json()["vocabulary_id"]
    words = client.get(f"/api/v1/vocabularies/{vocabulary_id}/words")
    assert words.status_code == 200
    entry = words.json()["items"][0]
    assert entry["term"] == "in order to"
    assert entry["entry_type"] == "phrase"


def test_csv_file_import_succeeds(client: TestClient) -> None:
    content = b"term,meaning,pos\napple,fruit,noun"
    preview_response = client.post(
        "/api/v1/vocabularies/import/preview",
        data={"name": "CSV words"},
        files={"file": ("words.csv", content, "text/csv")},
    )

    assert preview_response.status_code == 200
    preview = preview_response.json()
    response = client.post(
        "/api/v1/vocabularies/import",
        data={
            "name": "CSV words",
            "preview_digest": preview["preview_digest"],
        },
        files={"file": ("words.csv", content, "text/csv")},
    )

    assert response.status_code == 201
    assert response.json()["imported"] == 1


def test_valid_rows_are_imported_when_other_rows_fail(client: TestClient) -> None:
    text = "term|meaning\nvalid|有效\nmissing|\nVALID|重复"
    preview = preview_text(client, text)

    response = commit_text(client, text, preview)

    assert response.status_code == 201
    body = response.json()
    assert body["imported"] == 1
    assert body["duplicated"] == 1
    assert {error["code"] for error in body["errors"]} == {
        "EMPTY_MEANING",
        "DUPLICATE_TERM",
    }


def test_empty_vocabulary_is_rejected(client: TestClient) -> None:
    text = "term|meaning\nmissing|"
    preview = preview_text(client, text)

    response = commit_text(client, text, preview)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "EMPTY_VOCABULARY"


def test_changed_content_cannot_be_committed(client: TestClient) -> None:
    preview = preview_text(client, "apple|fruit")

    response = commit_text(client, "pear|fruit", preview)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PREVIEW_MISMATCH"


def test_unsupported_file_type_returns_415(client: TestClient) -> None:
    response = client.post(
        "/api/v1/vocabularies/import/preview",
        data={"name": "Spreadsheet"},
        files={"file": ("words.xlsx", b"not excel", "application/octet-stream")},
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_delete_requires_matching_confirmation(client: TestClient) -> None:
    text = "apple|fruit"
    imported = commit_text(client, text, preview_text(client, text))
    vocabulary_id = imported.json()["vocabulary_id"]

    missing = client.delete(f"/api/v1/vocabularies/{vocabulary_id}")
    assert missing.status_code == 409
    assert missing.json()["error"]["code"] == "CONFIRMATION_REQUIRED"

    rejected = client.delete(
        f"/api/v1/vocabularies/{vocabulary_id}",
        params={"confirm_id": vocabulary_id + 1},
    )
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "CONFIRMATION_REQUIRED"

    deleted = client.delete(
        f"/api/v1/vocabularies/{vocabulary_id}",
        params={"confirm_id": vocabulary_id},
    )
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/vocabularies/{vocabulary_id}").status_code == 404


def test_delete_cascades_state_but_retains_history_and_statistics(
    client: TestClient,
) -> None:
    text = "term|meaning\nfocus|attention"
    imported = commit_text(
        client,
        text,
        preview_text(client, text, name="History"),
        name="History",
    )
    vocabulary_id = imported.json()["vocabulary_id"]
    session_factory = client.app.state.session_factory
    local_today = datetime.now(ZoneInfo("Asia/Shanghai")).date()

    with session_factory() as session:
        entry = session.scalar(
            select(Entry).where(Entry.vocabulary_id == vocabulary_id)
        )
        assert entry is not None
        session.add(StudyPlan(vocabulary_id=vocabulary_id, daily_new_limit=10))
        session.add(ReviewState(entry_id=entry.id, box_number=2))
        for offset in (1, 0):
            activity_date = local_today - timedelta(days=offset)
            session.add(
                LearningEvent(
                    entry_id=entry.id,
                    term_key=entry.normalized_term,
                    term_snapshot=entry.term,
                    vocabulary_id_snapshot=vocabulary_id,
                    vocabulary_name_snapshot="History",
                    result="remembered",
                    attempts=1,
                    occurred_at=datetime.now(UTC),
                    timezone="Asia/Shanghai",
                    activity_date=activity_date,
                )
            )
        session.commit()

    before = client.get("/api/v1/statistics")
    assert before.status_code == 200
    assert before.json() == {
        "total_events": 2,
        "learned_days": 2,
        "streak": 2,
    }

    deleted = client.delete(
        f"/api/v1/vocabularies/{vocabulary_id}",
        params={"confirm_id": vocabulary_id},
    )
    assert deleted.status_code == 204

    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Entry)) == 0
        assert session.scalar(select(func.count()).select_from(StudyPlan)) == 0
        assert session.scalar(select(func.count()).select_from(ReviewState)) == 0
        events = list(session.scalars(select(LearningEvent)))
        assert len(events) == 2
        assert all(event.entry_id is None for event in events)
        assert {event.term_snapshot for event in events} == {"focus"}
        assert {event.vocabulary_name_snapshot for event in events} == {"History"}

    after = client.get("/api/v1/statistics")
    assert after.status_code == 200
    assert after.json() == before.json()


def test_list_search_sort_pagination_and_tag_filter(client: TestClient) -> None:
    first_text = "term|meaning|tags\nzebra|animal|Nature\napple|fruit|food"
    second_text = "term|meaning\nfocus|attention"
    commit_text(
        client,
        first_text,
        preview_text(client, first_text, name="Animals"),
        name="Animals",
    )
    second = commit_text(
        client,
        second_text,
        preview_text(client, second_text, name="Study"),
        name="Study",
    )

    page = client.get(
        "/api/v1/vocabularies",
        params={"q": "stu", "sort": "name", "order": "asc", "page_size": 1},
    )
    assert page.status_code == 200
    assert page.json()["total"] == 1
    assert page.json()["items"][0]["name"] == "Study"

    first_page = client.get(
        "/api/v1/vocabularies",
        params={"sort": "name", "order": "asc", "page_size": 1, "page": 1},
    )
    second_page = client.get(
        "/api/v1/vocabularies",
        params={"sort": "name", "order": "asc", "page_size": 1, "page": 2},
    )
    assert first_page.json()["total"] == 2
    assert first_page.json()["items"][0]["name"] == "Animals"
    assert second_page.json()["items"][0]["name"] == "Study"

    animals = client.get(
        "/api/v1/vocabularies",
        params={"q": "Animals"},
    ).json()[
        "items"
    ][0]
    words = client.get(
        f"/api/v1/vocabularies/{animals['id']}/words",
        params={"q": "a", "tag": "nature", "sort": "term", "order": "desc"},
    )
    assert words.status_code == 200
    assert [item["term"] for item in words.json()["items"]] == ["zebra"]
    sorted_words = client.get(
        f"/api/v1/vocabularies/{animals['id']}/words",
        params={"q": "a", "sort": "term", "order": "desc"},
    )
    assert [item["term"] for item in sorted_words.json()["items"]] == [
        "zebra",
        "apple",
    ]
    assert second.status_code == 201
