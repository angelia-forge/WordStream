import pytest

from app.services.import_parser import (
    ImportFormatError,
    parse_import,
    resolve_file_type,
)


@pytest.mark.parametrize(
    ("separator", "content"),
    [
        ("pipe", "apple | 苹果"),
        ("fullwidth_pipe", "apple \uff5c 苹果"),
        ("tab", "apple\t苹果"),
        ("comma", "apple,苹果"),
        ("spaces", "apple  苹果"),
    ],
)
def test_delimiter_is_detected(separator: str, content: str) -> None:
    result = parse_import(content.encode(), file_type=".txt")

    assert separator
    assert result.entries[0].term == "apple"
    assert result.entries[0].meaning == "苹果"


def test_chinese_headers_are_mapped() -> None:
    result = parse_import(
        (
            "单词,释义,词性,音标,例句,标签,类型\n"
            "focus,专注,noun,/\u02c8fəʊkəs/,"
            '"Keep focus, please","学习,核心",word'
        ).encode(),
        file_type=".csv",
    )

    entry = result.entries[0]
    assert entry.part_of_speech == "noun"
    assert entry.phonetic == "/\u02c8fəʊkəs/"
    assert entry.example == "Keep focus, please"
    assert entry.tags == ["学习", "核心"]


def test_phrase_keeps_collapsed_semantic_spaces() -> None:
    result = parse_import("in   order to | 为了".encode(), file_type=".txt")

    entry = result.entries[0]
    assert entry.term == "in order to"
    assert entry.normalized_term == "in order to"
    assert entry.entry_type == "phrase"


@pytest.mark.parametrize(
    ("content", "code"),
    [
        ("| meaning", "EMPTY_TERM"),
        ("word | ", "EMPTY_MEANING"),
    ],
)
def test_required_values_are_reported(content: str, code: str) -> None:
    result = parse_import(content.encode(), file_type=".txt")

    assert result.entries == []
    assert result.errors[0].code == code


def test_duplicate_term_keeps_first_valid_record() -> None:
    result = parse_import(
        b"Word | first\n word | second",
        file_type=".txt",
    )

    assert [entry.meaning for entry in result.entries] == ["first"]
    assert result.duplicated == 1
    assert result.errors[0].code == "DUPLICATE_TERM"


def test_utf8_bom_is_removed() -> None:
    result = parse_import(
        "\ufeffterm,meaning\napple,苹果".encode(),
        file_type=".csv",
    )

    assert result.entries[0].term == "apple"


def test_csv_quotes_newlines_and_special_characters() -> None:
    result = parse_import(
        (
            'term,meaning,example\nhello,"问候,招呼",' '"She said ""hello"".\nAgain."'
        ).encode(),
        file_type=".csv",
    )

    entry = result.entries[0]
    assert entry.meaning == "问候,招呼"
    assert entry.example == 'She said "hello".\nAgain.'


def test_recognized_header_without_required_columns_is_rejected() -> None:
    with pytest.raises(ImportFormatError) as error:
        parse_import(b"word,pos\nhello,noun", file_type=".csv")

    assert error.value.code == "MISSING_REQUIRED_COLUMNS"


def test_json_requires_object_array() -> None:
    with pytest.raises(ImportFormatError) as error:
        parse_import(b'{"term":"hello"}', file_type=".json")

    assert error.value.code == "INVALID_IMPORT_FORMAT"


def test_empty_json_array_has_no_entries() -> None:
    result = parse_import(b"[]", file_type=".json")

    assert result.entries == []
    assert result.errors == []


def test_json_requires_mappable_columns_across_document() -> None:
    with pytest.raises(ImportFormatError) as error:
        parse_import(b'[{"word":"hello","pos":"noun"}]', file_type=".json")

    assert error.value.code == "MISSING_REQUIRED_COLUMNS"


def test_json_missing_field_is_a_row_error() -> None:
    result = parse_import(
        '[{"term":"hello","meaning":"问候"},{"term":"bye"}]'.encode(),
        file_type=".json",
    )

    assert len(result.entries) == 1
    assert result.errors[0].code == "EMPTY_MEANING"


def test_json_explicit_phrase_type_is_mapped() -> None:
    result = parse_import(
        '[{"term":"ice cream","meaning":"冰淇淋","type":"word"}]'.encode(),
        file_type=".json",
    )

    assert result.entries[0].entry_type == "word"


def test_unsupported_file_type_is_rejected() -> None:
    with pytest.raises(ImportFormatError) as error:
        resolve_file_type("words.xlsx", None)

    assert error.value.code == "UNSUPPORTED_FILE_TYPE"
