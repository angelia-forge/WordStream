from __future__ import annotations

from pathlib import Path
from typing import Literal

from app.exceptions import AppError
from app.models.vocabulary import Entry, Vocabulary
from app.schemas.vocabularies import (
    EntryPage,
    EntryRead,
    ImportPreview,
    ImportResult,
    VocabularyPage,
    VocabularyRead,
)
from app.services.import_parser import (
    ImportFormatError,
    ParsedImport,
    parse_import,
    preview_digest,
)
from app.unit_of_work import AbstractUnitOfWork

VocabularySort = Literal["created_at", "name", "entry_count"]
EntrySort = Literal["term", "created_at", "part_of_speech", "entry_type"]
SortOrder = Literal["asc", "desc"]


class VocabularyService:
    def __init__(self, uow: AbstractUnitOfWork) -> None:
        self._uow = uow

    def preview(
        self,
        payload: bytes,
        *,
        file_type: str,
        source_filename: str | None,
        name: str,
        duplicate_policy: str,
    ) -> ImportPreview:
        parsed = self._parse(payload, file_type=file_type)
        return ImportPreview(
            preview_digest=preview_digest(
                payload,
                name=name,
                duplicate_policy=duplicate_policy,
                source_filename=source_filename,
            ),
            source_filename=source_filename,
            imported=len(parsed.entries),
            duplicated=parsed.duplicated,
            errors=parsed.errors,
            entries=parsed.entries,
        )

    def import_vocabulary(
        self,
        payload: bytes,
        *,
        file_type: str,
        source_filename: str | None,
        name: str,
        duplicate_policy: str,
        expected_digest: str,
    ) -> ImportResult:
        actual_digest = preview_digest(
            payload,
            name=name,
            duplicate_policy=duplicate_policy,
            source_filename=source_filename,
        )
        if actual_digest != expected_digest:
            raise AppError(
                "PREVIEW_MISMATCH",
                "Import content or options changed after preview",
                status_code=409,
            )

        parsed = self._parse(payload, file_type=file_type)
        if not parsed.entries:
            raise AppError(
                "EMPTY_VOCABULARY",
                "No valid entries were found",
                status_code=422,
                details=[issue.model_dump() for issue in parsed.errors],
            )

        with self._uow:
            vocabulary = Vocabulary(
                name=name.strip(),
                source_filename=(
                    Path(source_filename).name if source_filename else None
                ),
                entry_count=len(parsed.entries),
            )
            self._uow.vocabularies.add(vocabulary)
            self._uow.vocabularies.add_entries(
                [
                    Entry(
                        vocabulary_id=vocabulary.id,
                        term=item.term,
                        normalized_term=item.normalized_term,
                        entry_type=item.entry_type,
                        meaning=item.meaning,
                        part_of_speech=item.part_of_speech,
                        phonetic=item.phonetic,
                        example=item.example,
                        tags=item.tags,
                    )
                    for item in parsed.entries
                ]
            )
            self._uow.commit()
            return ImportResult(
                vocabulary_id=vocabulary.id,
                imported=len(parsed.entries),
                duplicated=parsed.duplicated,
                errors=parsed.errors,
            )

    def list_vocabularies(
        self,
        *,
        page: int,
        page_size: int,
        query: str | None,
        sort: VocabularySort,
        order: SortOrder,
    ) -> VocabularyPage:
        sort_columns = {
            "created_at": Vocabulary.created_at,
            "name": Vocabulary.name,
            "entry_count": Vocabulary.entry_count,
        }
        with self._uow:
            items, total = self._uow.vocabularies.list(
                page=page,
                page_size=page_size,
                query=query,
                sort_column=sort_columns[sort],
                descending=order == "desc",
            )
            return VocabularyPage(
                items=[VocabularyRead.model_validate(item) for item in items],
                page=page,
                page_size=page_size,
                total=total,
            )

    def get_vocabulary(self, vocabulary_id: int) -> VocabularyRead:
        with self._uow:
            vocabulary = self._require_vocabulary(vocabulary_id)
            return VocabularyRead.model_validate(vocabulary)

    def list_entries(
        self,
        vocabulary_id: int,
        *,
        page: int,
        page_size: int,
        query: str | None,
        tag: str | None,
        sort: EntrySort,
        order: SortOrder,
    ) -> EntryPage:
        sort_columns = {
            "term": Entry.term,
            "created_at": Entry.created_at,
            "part_of_speech": Entry.part_of_speech,
            "entry_type": Entry.entry_type,
        }
        with self._uow:
            self._require_vocabulary(vocabulary_id)
            items, total = self._uow.vocabularies.list_entries(
                vocabulary_id,
                page=page,
                page_size=page_size,
                query=query,
                tag=tag,
                sort_column=sort_columns[sort],
                descending=order == "desc",
            )
            return EntryPage(
                items=[EntryRead.model_validate(item) for item in items],
                page=page,
                page_size=page_size,
                total=total,
            )

    def delete(self, vocabulary_id: int, *, confirm_id: int) -> None:
        if confirm_id != vocabulary_id:
            raise AppError(
                "CONFIRMATION_REQUIRED",
                "confirm_id must match the vocabulary id",
                status_code=409,
            )
        with self._uow:
            vocabulary = self._require_vocabulary(vocabulary_id)
            self._uow.vocabularies.delete(vocabulary)
            self._uow.commit()

    def _require_vocabulary(self, vocabulary_id: int) -> Vocabulary:
        vocabulary = self._uow.vocabularies.get(vocabulary_id)
        if vocabulary is None:
            raise AppError(
                "RESOURCE_NOT_FOUND",
                "Vocabulary was not found",
                status_code=404,
            )
        return vocabulary

    @staticmethod
    def _parse(payload: bytes, *, file_type: str) -> ParsedImport:
        try:
            return parse_import(payload, file_type=file_type)
        except ImportFormatError as exc:
            status_code = 415 if exc.code == "UNSUPPORTED_FILE_TYPE" else 422
            raise AppError(
                exc.code,
                exc.message,
                status_code=status_code,
            ) from exc
