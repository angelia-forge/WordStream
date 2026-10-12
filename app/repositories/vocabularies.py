from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.models.vocabulary import Entry, Vocabulary


class VocabularyRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, vocabulary: Vocabulary) -> None:
        self._session.add(vocabulary)
        self._session.flush()

    def add_entries(self, entries: Sequence[Entry]) -> None:
        self._session.add_all(entries)
        self._session.flush()

    def get(self, vocabulary_id: int) -> Vocabulary | None:
        return self._session.get(Vocabulary, vocabulary_id)

    def delete(self, vocabulary: Vocabulary) -> None:
        self._session.delete(vocabulary)

    def list(
        self,
        *,
        page: int,
        page_size: int,
        query: str | None,
        sort_column: InstrumentedAttribute[Any],
        descending: bool,
    ) -> tuple[Sequence[Vocabulary], int]:
        statement = select(Vocabulary)
        count_statement = select(func.count()).select_from(Vocabulary)
        if query:
            predicate = Vocabulary.name.ilike(f"%{query}%")
            statement = statement.where(predicate)
            count_statement = count_statement.where(predicate)

        order_expression = sort_column.desc() if descending else sort_column.asc()
        statement = statement.order_by(order_expression, Vocabulary.id.asc())
        statement = statement.offset((page - 1) * page_size).limit(page_size)
        items = list(self._session.scalars(statement))
        total = self._session.scalar(count_statement) or 0
        return items, total

    def list_entries(
        self,
        vocabulary_id: int,
        *,
        page: int,
        page_size: int,
        query: str | None,
        tag: str | None,
        sort_column: InstrumentedAttribute[Any],
        descending: bool,
    ) -> tuple[Sequence[Entry], int]:
        statement = select(Entry).where(Entry.vocabulary_id == vocabulary_id)
        count_statement = (
            select(func.count())
            .select_from(Entry)
            .where(Entry.vocabulary_id == vocabulary_id)
        )
        if query:
            predicate = or_(
                Entry.term.ilike(f"%{query}%"),
                Entry.meaning.ilike(f"%{query}%"),
            )
            statement = statement.where(predicate)
            count_statement = count_statement.where(predicate)
        if tag:
            json_tags = func.json_each(Entry.tags).table_valued("key", "value")
            predicate = exists(
                select(1)
                .select_from(json_tags)
                .where(func.lower(json_tags.c.value) == tag.lower())
            )
            statement = statement.where(predicate)
            count_statement = count_statement.where(predicate)

        order_expression = sort_column.desc() if descending else sort_column.asc()
        statement = statement.order_by(order_expression, Entry.id.asc())
        statement = statement.offset((page - 1) * page_size).limit(page_size)
        items = list(self._session.scalars(statement))
        total = self._session.scalar(count_statement) or 0
        return items, total
