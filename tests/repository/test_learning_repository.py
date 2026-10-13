from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from sqlalchemy.orm import Session

from app.config import AuthMode, Environment, Settings
from app.db import create_database_engine, create_session_factory
from app.models.learning import LearningEvent, ReviewState
from app.models.vocabulary import Entry, Vocabulary
from app.repositories.learning import LearningRepository


def test_learning_repository_queries_real_sqlite_file(database_url: str) -> None:
    engine = create_database_engine(
        Settings(
            environment=Environment.TEST,
            auth_mode=AuthMode.DISABLED,
            database_url=database_url,
        )
    )
    session_factory = create_session_factory(engine)
    today = date(2026, 10, 13)
    now = datetime(2026, 10, 13, 8, tzinfo=UTC)

    try:
        with session_factory() as session:
            first, second = _seed_vocabularies(session)
            session.add_all(
                [
                    _event(first, today=today),
                    _event(first, today=today),
                    _event(second, today=today - timedelta(days=1)),
                    ReviewState(
                        entry_id=first.id,
                        box_number=0,
                        next_review_at=now - timedelta(seconds=1),
                    ),
                    ReviewState(
                        entry_id=second.id,
                        box_number=1,
                        next_review_at=now + timedelta(days=1),
                    ),
                ]
            )
            session.commit()

            repository = LearningRepository(session)
            assert repository.event_count() == 3
            assert repository.activity_dates() == [
                today,
                today - timedelta(days=1),
            ]
            assert repository.activity_dates(vocabulary_id=first.vocabulary_id) == [
                today
            ]
            assert repository.distinct_terms_on(today) == 1
            assert repository.due_review_count(now=now) == 1
            assert (
                repository.due_review_count(
                    now=now,
                    vocabulary_id=second.vocabulary_id,
                )
                == 0
            )
            assert repository.entry_count() == 2
            assert repository.entry_count(vocabulary_id=first.vocabulary_id) == 1
    finally:
        engine.dispose()


def _seed_vocabularies(session: Session) -> tuple[Entry, Entry]:
    first_vocabulary = Vocabulary(name="First", entry_count=1)
    second_vocabulary = Vocabulary(name="Second", entry_count=1)
    session.add_all([first_vocabulary, second_vocabulary])
    session.flush()
    first = Entry(
        vocabulary_id=first_vocabulary.id,
        term="alpha",
        normalized_term="alpha",
        entry_type="word",
        meaning="first",
        tags=[],
    )
    second = Entry(
        vocabulary_id=second_vocabulary.id,
        term="bravo",
        normalized_term="bravo",
        entry_type="word",
        meaning="second",
        tags=[],
    )
    session.add_all([first, second])
    session.flush()
    return first, second


def _event(entry: Entry, *, today: date) -> LearningEvent:
    return LearningEvent(
        client_event_id=str(uuid4()),
        entry_id=entry.id,
        term_key=entry.normalized_term,
        term_snapshot=entry.term,
        vocabulary_snapshot={
            "id": entry.vocabulary_id,
            "name": entry.vocabulary.name,
        },
        result="seen",
        attempt_count=1,
        client_attempt_count=1,
        occurred_at=datetime(2026, 10, 13, 8, tzinfo=UTC),
        timezone="UTC",
        activity_date=today,
    )
