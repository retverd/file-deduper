"""Тесты сравнения папок."""

import logging
import sys
from collections import Counter
from pathlib import Path

import pytest

import folder_compare
from folder_compare import (
    FileRecord,
    identity_counter,
    index_folder,
    records_with_common_hash_metadata_diff,
    records_with_unique_hashes,
)


def make_record(
    checksum: str,
    relative_path: str,
    *,
    size: int = 1,
    name: str | None = None,
) -> FileRecord:
    """Создает FileRecord для синтетических сценариев сравнения папок."""
    file_name = name if name is not None else relative_path.split("/")[-1]
    return FileRecord(
        checksum=checksum,
        size=size,
        relative_path=relative_path,
        name=file_name,
    )


def test_identity_counter_counts_matching_identities() -> None:
    """Считает количество файлов по паре (контрольная сумма, относительный путь)."""
    records = [
        make_record("h1", "a.txt"),
        make_record("h1", "b.txt"),
        make_record("h2", "c.txt"),
    ]

    counter = identity_counter(records)

    assert counter == Counter(
        {("h1", "a.txt"): 1, ("h1", "b.txt"): 1, ("h2", "c.txt"): 1}
    )


def test_records_with_common_hash_metadata_diff_finds_unmatched_paths() -> None:
    """Находит файлы с общим хэшем, для которых нет пары по пути в другой папке."""
    first = [
        make_record("h1", "a.txt"),
        make_record("h1", "b.txt"),
    ]
    second = [make_record("h1", "a.txt")]

    first_diff, second_diff = records_with_common_hash_metadata_diff(first, second)

    assert [record.relative_path for record in first_diff] == ["b.txt"]
    assert second_diff == []


def test_records_with_common_hash_metadata_diff_reports_both_sides() -> None:
    """Возвращает различия с обеих сторон, если совпадает только содержимое."""
    first = [make_record("h1", "old.txt")]
    second = [make_record("h1", "new.txt")]

    first_diff, second_diff = records_with_common_hash_metadata_diff(first, second)

    assert [record.relative_path for record in first_diff] == ["old.txt"]
    assert [record.relative_path for record in second_diff] == ["new.txt"]


def test_records_with_common_hash_metadata_diff_ignores_unique_hashes() -> None:
    """Не включает файлы, хэши которых есть только в одной из папок."""
    first = [make_record("h1", "a.txt")]
    second = [make_record("h2", "b.txt")]

    first_diff, second_diff = records_with_common_hash_metadata_diff(first, second)

    assert first_diff == []
    assert second_diff == []


def test_records_with_unique_hashes() -> None:
    """Выделяет файлы, SHA-256 которых отсутствует в другой папке."""
    first = [
        make_record("h1", "shared.txt"),
        make_record("h2", "only-first.txt"),
    ]
    second = [
        make_record("h1", "shared.txt"),
        make_record("h3", "only-second.txt"),
    ]

    unique_first = records_with_unique_hashes(first, second)
    unique_second = records_with_unique_hashes(second, first)

    assert [record.relative_path for record in unique_first] == ["only-first.txt"]
    assert [record.relative_path for record in unique_second] == ["only-second.txt"]


def test_index_folder_reports_read_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Помечает ошибки чтения, но собирает остальные файлы."""
    logger = logging.getLogger("test_index_folder")
    readable = tmp_path / "readable.txt"
    unreadable = tmp_path / "unreadable.txt"
    readable.write_text("data", encoding="utf-8")
    unreadable.write_text("secret", encoding="utf-8")

    original_build_file_record = folder_compare.build_file_record

    def failing_build_file_record(root: Path, file_path: Path) -> FileRecord:
        if file_path.name == "unreadable.txt":
            raise OSError("нет доступа")
        return original_build_file_record(root, file_path)

    monkeypatch.setattr(
        folder_compare, "build_file_record", failing_build_file_record
    )

    records, had_read_errors = index_folder(tmp_path, logger)

    assert had_read_errors is True
    assert [record.name for record in records] == ["readable.txt"]


def test_main_stops_on_read_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Возвращает код 1, если при индексации хотя бы одного файла была ошибка."""
    first_folder = tmp_path / "first"
    second_folder = tmp_path / "second"
    first_folder.mkdir()
    second_folder.mkdir()
    (first_folder / "broken.txt").write_text("data", encoding="utf-8")
    (second_folder / "ok.txt").write_text("data", encoding="utf-8")
    log_path = tmp_path / "compare.log"

    original_build_file_record = folder_compare.build_file_record

    def failing_build_file_record(root: Path, file_path: Path) -> FileRecord:
        if file_path.name == "broken.txt":
            raise OSError("нет доступа")
        return original_build_file_record(root, file_path)

    monkeypatch.setattr(
        folder_compare, "build_file_record", failing_build_file_record
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["folder_compare.py", str(first_folder), str(second_folder)],
    )
    monkeypatch.setattr(
        folder_compare, "build_log_path", lambda prefix="compare": log_path
    )

    assert folder_compare.main() == 1


def test_main_returns_error_for_invalid_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Возвращает код 1, если хотя бы один путь не является папкой."""
    valid_folder = tmp_path / "valid"
    valid_folder.mkdir()
    invalid_path = tmp_path / "missing_folder"
    log_path = tmp_path / "compare.log"

    monkeypatch.setattr(
        sys,
        "argv",
        ["folder_compare.py", str(valid_folder), str(invalid_path)],
    )
    monkeypatch.setattr(
        folder_compare, "build_log_path", lambda prefix="compare": log_path
    )

    assert folder_compare.main() == 1
