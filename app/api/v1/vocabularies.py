from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, Query, Response, UploadFile

from app.dependencies import AccessDep, ConfigDep, UowDep
from app.exceptions import AppError
from app.schemas.vocabularies import (
    EntryPage,
    ImportPreview,
    ImportResult,
    VocabularyPage,
    VocabularyRead,
)
from app.services.import_parser import ImportFormatError, resolve_file_type
from app.services.vocabularies import VocabularyService

router = APIRouter(prefix="/vocabularies", tags=["vocabularies"])


@router.post("/import/preview", response_model=ImportPreview)
async def preview_import(
    config: ConfigDep,
    uow: UowDep,
    _: AccessDep,
    name: Annotated[str, Form(min_length=1, max_length=200)],
    duplicate_policy: Annotated[Literal["skip"], Form()] = "skip",
    text: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> ImportPreview:
    payload, file_type, source_filename = await _read_source(
        config,
        text=text,
        file=file,
    )
    _validate_name(name)
    return VocabularyService(uow).preview(
        payload,
        file_type=file_type,
        source_filename=source_filename,
        name=name.strip(),
        duplicate_policy=duplicate_policy,
    )


@router.post("/import", response_model=ImportResult, status_code=201)
async def import_vocabulary(
    config: ConfigDep,
    uow: UowDep,
    _: AccessDep,
    name: Annotated[str, Form(min_length=1, max_length=200)],
    preview_digest: Annotated[str, Form(min_length=64, max_length=64)],
    duplicate_policy: Annotated[Literal["skip"], Form()] = "skip",
    text: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> ImportResult:
    payload, file_type, source_filename = await _read_source(
        config,
        text=text,
        file=file,
    )
    _validate_name(name)
    return VocabularyService(uow).import_vocabulary(
        payload,
        file_type=file_type,
        source_filename=source_filename,
        name=name.strip(),
        duplicate_policy=duplicate_policy,
        expected_digest=preview_digest,
    )


@router.get("", response_model=VocabularyPage)
def list_vocabularies(
    uow: UowDep,
    _: AccessDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    q: Annotated[str | None, Query(max_length=200)] = None,
    sort: Literal["created_at", "name", "entry_count"] = "created_at",
    order: Literal["asc", "desc"] = "desc",
) -> VocabularyPage:
    return VocabularyService(uow).list_vocabularies(
        page=page,
        page_size=page_size,
        query=q,
        sort=sort,
        order=order,
    )


@router.get("/{vocabulary_id}", response_model=VocabularyRead)
def get_vocabulary(
    vocabulary_id: int,
    uow: UowDep,
    _: AccessDep,
) -> VocabularyRead:
    return VocabularyService(uow).get_vocabulary(vocabulary_id)


@router.get("/{vocabulary_id}/words", response_model=EntryPage)
def list_entries(
    vocabulary_id: int,
    uow: UowDep,
    _: AccessDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    q: Annotated[str | None, Query(max_length=500)] = None,
    tag: Annotated[str | None, Query(max_length=100)] = None,
    sort: Literal["term", "created_at", "part_of_speech", "entry_type"] = "term",
    order: Literal["asc", "desc"] = "asc",
) -> EntryPage:
    return VocabularyService(uow).list_entries(
        vocabulary_id,
        page=page,
        page_size=page_size,
        query=q,
        tag=tag,
        sort=sort,
        order=order,
    )


@router.delete("/{vocabulary_id}", status_code=204)
def delete_vocabulary(
    vocabulary_id: int,
    uow: UowDep,
    _: AccessDep,
    confirm_id: int | None = None,
) -> Response:
    VocabularyService(uow).delete(vocabulary_id, confirm_id=confirm_id)
    return Response(status_code=204)


async def _read_source(
    config: ConfigDep,
    *,
    text: str | None,
    file: UploadFile | None,
) -> tuple[bytes, str, str | None]:
    if (text is None) == (file is None):
        raise AppError(
            "INVALID_IMPORT_FORMAT",
            "Provide exactly one of text or file",
            status_code=422,
        )
    if file is None:
        assert text is not None
        payload = text.encode()
        if len(payload) > config.import_max_bytes:
            _raise_payload_too_large(config.import_max_bytes)
        return payload, ".txt", None

    source_filename = Path(file.filename or "").name
    try:
        file_type = resolve_file_type(source_filename, file.content_type)
    except ImportFormatError as exc:
        raise AppError(exc.code, exc.message, status_code=415) from exc

    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(65_536):
        total += len(chunk)
        if total > config.import_max_bytes:
            _raise_payload_too_large(config.import_max_bytes)
        chunks.append(chunk)
    return b"".join(chunks), file_type, source_filename or None


def _validate_name(name: str) -> None:
    if not name.strip():
        raise AppError(
            "VALIDATION_ERROR",
            "Vocabulary name is required",
            status_code=422,
        )


def _raise_payload_too_large(max_bytes: int) -> None:
    raise AppError(
        "PAYLOAD_TOO_LARGE",
        f"Import payload exceeds {max_bytes} bytes",
        status_code=413,
    )
