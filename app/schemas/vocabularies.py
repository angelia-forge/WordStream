from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

EntryType = Literal["word", "phrase"]


class ImportEntry(BaseModel):
    term: str
    normalized_term: str
    entry_type: EntryType
    meaning: str
    part_of_speech: str | None = None
    phonetic: str | None = None
    example: str | None = None
    tags: list[str]


class ImportIssue(BaseModel):
    line: int
    code: str
    reason: str
    raw: str


class ImportPreview(BaseModel):
    preview_digest: str
    source_filename: str | None
    imported: int
    duplicated: int
    errors: list[ImportIssue]
    entries: list[ImportEntry]


class ImportResult(BaseModel):
    vocabulary_id: int
    imported: int
    duplicated: int
    errors: list[ImportIssue]


class VocabularyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    source_filename: str | None
    entry_count: int
    created_at: datetime


class VocabularyPage(BaseModel):
    items: list[VocabularyRead]
    page: int
    page_size: int
    total: int


class EntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vocabulary_id: int
    term: str
    normalized_term: str
    entry_type: EntryType
    meaning: str
    part_of_speech: str | None
    phonetic: str | None
    example: str | None
    tags: list[str]
    created_at: datetime


class EntryPage(BaseModel):
    items: list[EntryRead]
    page: int
    page_size: int
    total: int
