from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.schemas.vocabularies import ImportEntry, ImportIssue

HEADER_ALIASES = {
    "term": "term",
    "word": "term",
    "单词": "term",
    "meaning": "meaning",
    "词义": "meaning",
    "释义": "meaning",
    "pos": "part_of_speech",
    "part_of_speech": "part_of_speech",
    "词性": "part_of_speech",
    "phonetic": "phonetic",
    "音标": "phonetic",
    "example": "example",
    "例句": "example",
    "tags": "tags",
    "标签": "tags",
    "type": "entry_type",
    "类型": "entry_type",
}
POSITIONAL_FIELDS = ("term", "meaning", "part_of_speech", "phonetic")
SUPPORTED_SUFFIXES = {".csv", ".tsv", ".txt", ".json"}
MIME_SUFFIXES = {
    "text/csv": ".csv",
    "text/tab-separated-values": ".tsv",
    "text/plain": ".txt",
    "application/json": ".json",
}


class ImportFormatError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ParsedImport:
    entries: list[ImportEntry]
    errors: list[ImportIssue]
    duplicated: int


def normalize_term(value: str) -> tuple[str, str]:
    term = " ".join(value.split())
    return term, term.lower()


def preview_digest(
    payload: bytes,
    *,
    name: str,
    duplicate_policy: str,
    source_filename: str | None,
) -> str:
    metadata = json.dumps(
        {
            "name": name,
            "duplicate_policy": duplicate_policy,
            "source_filename": source_filename,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(metadata + b"\0" + payload).hexdigest()


def resolve_file_type(filename: str, content_type: str | None) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix:
        if suffix not in SUPPORTED_SUFFIXES:
            raise ImportFormatError(
                "UNSUPPORTED_FILE_TYPE",
                "Only CSV, TSV, TXT, and JSON files are supported",
            )
        return suffix
    resolved = MIME_SUFFIXES.get((content_type or "").split(";", 1)[0].lower())
    if resolved is None:
        raise ImportFormatError(
            "UNSUPPORTED_FILE_TYPE",
            "Only CSV, TSV, TXT, and JSON files are supported",
        )
    return resolved


def parse_import(payload: bytes, *, file_type: str) -> ParsedImport:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportFormatError(
            "INVALID_IMPORT_FORMAT",
            "Import content must use UTF-8 encoding",
        ) from exc

    if file_type == ".json":
        return _parse_json(text)
    forced_delimiter = "\t" if file_type == ".tsv" else None
    return _parse_delimited(text, forced_delimiter=forced_delimiter)


def _parse_json(text: str) -> ParsedImport:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ImportFormatError(
            "INVALID_IMPORT_FORMAT",
            f"Invalid JSON at line {exc.lineno}",
        ) from exc
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ImportFormatError(
            "INVALID_IMPORT_FORMAT",
            "JSON must be an array of objects",
        )
    if not value:
        return ParsedImport(entries=[], errors=[], duplicated=0)

    mapped_keys = {
        HEADER_ALIASES[key.strip().lower()]
        for item in value
        for key in item
        if key.strip().lower() in HEADER_ALIASES
    }
    if not {"term", "meaning"}.issubset(mapped_keys):
        raise ImportFormatError(
            "MISSING_REQUIRED_COLUMNS",
            "Import data must include term and meaning columns",
        )

    rows: list[tuple[int, dict[str, Any], str]] = []
    for index, item in enumerate(value, start=1):
        mapped: dict[str, Any] = {}
        for key, field in HEADER_ALIASES.items():
            if key in {str(item_key).strip().lower() for item_key in item}:
                original_key = next(
                    item_key
                    for item_key in item
                    if str(item_key).strip().lower() == key
                )
                mapped.setdefault(field, item[original_key])
        rows.append(
            (
                index,
                mapped,
                json.dumps(item, ensure_ascii=False, separators=(",", ":")),
            )
        )
    return _validate_rows(rows)


def _parse_delimited(text: str, *, forced_delimiter: str | None) -> ParsedImport:
    if not text.strip():
        return ParsedImport(entries=[], errors=[], duplicated=0)

    delimiter = forced_delimiter or _detect_delimiter(text)
    if delimiter == "multi_space":
        raw_rows = [
            (line_number, re.split(r"\s{2,}", line.strip()), line)
            for line_number, line in enumerate(text.splitlines(), start=1)
            if line.strip()
        ]
    else:
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        raw_rows = [
            (reader.line_num, row, delimiter.join(row))
            for row in reader
            if any(value.strip() for value in row)
        ]

    if not raw_rows:
        return ParsedImport(entries=[], errors=[], duplicated=0)

    first_values = raw_rows[0][1]
    recognized = [HEADER_ALIASES.get(value.strip().lower()) for value in first_values]
    has_header = sum(field is not None for field in recognized) >= 2
    if has_header:
        field_indexes = {
            field: index for index, field in enumerate(recognized) if field is not None
        }
        if not {"term", "meaning"}.issubset(field_indexes):
            raise ImportFormatError(
                "MISSING_REQUIRED_COLUMNS",
                "Import data must include term and meaning columns",
            )
        data_rows = raw_rows[1:]
    else:
        field_indexes = {field: index for index, field in enumerate(POSITIONAL_FIELDS)}
        data_rows = raw_rows

    rows: list[tuple[int, dict[str, Any], str]] = []
    for line_number, values, raw in data_rows:
        mapped = {
            field: values[index] if index < len(values) else ""
            for field, index in field_indexes.items()
        }
        rows.append((line_number, mapped, raw))
    return _validate_rows(rows)


def _detect_delimiter(text: str) -> str:
    first_line = next((line for line in text.splitlines() if line.strip()), "")
    scored: list[tuple[int, int, str]] = []
    for priority, delimiter in enumerate(("|", "\uff5c", "\t", ",")):
        try:
            fields = next(csv.reader([first_line], delimiter=delimiter))
        except csv.Error:
            continue
        if len(fields) > 1:
            scored.append((len(fields), -priority, delimiter))
    if scored:
        return max(scored)[2]
    if re.search(r"\S\s{2,}\S", first_line):
        return "multi_space"
    raise ImportFormatError(
        "INVALID_IMPORT_FORMAT",
        "Could not detect a supported delimiter",
    )


def _validate_rows(
    rows: list[tuple[int, dict[str, Any], str]],
) -> ParsedImport:
    entries: list[ImportEntry] = []
    errors: list[ImportIssue] = []
    seen: set[str] = set()
    duplicated = 0

    for line_number, values, raw in rows:
        term, normalized_term = normalize_term(_string_value(values.get("term")))
        meaning = _string_value(values.get("meaning")).strip()
        if not term:
            errors.append(
                ImportIssue(
                    line=line_number,
                    code="EMPTY_TERM",
                    reason="term is required",
                    raw=raw,
                )
            )
            continue
        if not meaning:
            errors.append(
                ImportIssue(
                    line=line_number,
                    code="EMPTY_MEANING",
                    reason="meaning is required",
                    raw=raw,
                )
            )
            continue

        raw_type = _string_value(values.get("entry_type")).strip().lower()
        entry_type = raw_type or ("phrase" if " " in term else "word")
        if entry_type not in {"word", "phrase"}:
            errors.append(
                ImportIssue(
                    line=line_number,
                    code="INVALID_ENTRY_TYPE",
                    reason="type must be word or phrase",
                    raw=raw,
                )
            )
            continue
        if normalized_term in seen:
            duplicated += 1
            errors.append(
                ImportIssue(
                    line=line_number,
                    code="DUPLICATE_TERM",
                    reason="duplicate term was skipped",
                    raw=raw,
                )
            )
            continue

        seen.add(normalized_term)
        entries.append(
            ImportEntry(
                term=term,
                normalized_term=normalized_term,
                entry_type=entry_type,
                meaning=meaning,
                part_of_speech=_optional_string(values.get("part_of_speech")),
                phonetic=_optional_string(values.get("phonetic")),
                example=_optional_string(values.get("example")),
                tags=_parse_tags(values.get("tags")),
            )
        )
    return ParsedImport(entries=entries, errors=errors, duplicated=duplicated)


def _string_value(value: Any) -> str:
    return value if isinstance(value, str) else "" if value is None else str(value)


def _optional_string(value: Any) -> str | None:
    normalized = _string_value(value).strip()
    return normalized or None


def _parse_tags(value: Any) -> list[str]:
    raw_tags = (
        value
        if isinstance(value, list)
        else re.split(r"[,\uff0c;\uff1b]", _string_value(value))
    )
    tags: list[str] = []
    seen: set[str] = set()
    for raw_tag in raw_tags:
        tag = _string_value(raw_tag).strip()
        normalized = tag.lower()
        if tag and normalized not in seen:
            seen.add(normalized)
            tags.append(tag)
    return tags
