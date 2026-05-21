"""Тесты поиска дубликатов."""

import logging
import sys
from pathlib import Path

import pytest

import file_deduper
from file_deduper import find_duplicates


def test_find_duplicates_groups_identical_files(tmp_path: Path) -> None:
    """Объединяет файлы с одинаковым содержимым в одну группу дубликатов."""
    logger = logging.getLogger("test_file_deduper")
    (tmp_path / "a.txt").write_text("same", encoding="utf-8")
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "b.txt").write_text("same", encoding="utf-8")
    (tmp_path / "unique.txt").write_text("other", encoding="utf-8")

    duplicates = find_duplicates(tmp_path, logger)

    assert len(duplicates) == 1
    paths = next(iter(duplicates.values()))
    assert len(paths) == 2
    assert {path.name for path in paths} == {"a.txt", "b.txt"}


def test_find_duplicates_skips_unreadable_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Пропускает нечитаемые файлы и продолжает поиск без падения."""
    import file_deduper

    logger = logging.getLogger("test_file_deduper_unreadable")
    readable = tmp_path / "readable.txt"
    unreadable = tmp_path / "unreadable.txt"
    readable.write_text("data", encoding="utf-8")
    unreadable.write_text("secret", encoding="utf-8")

    original_calculate_checksum = file_deduper.calculate_checksum

    def fake_checksum(path: Path) -> str:
        if path.name == "unreadable.txt":
            raise OSError("нет доступа")
        return original_calculate_checksum(path)

    monkeypatch.setattr(file_deduper, "calculate_checksum", fake_checksum)

    duplicates = file_deduper.find_duplicates(tmp_path, logger)

    assert duplicates == {}


def test_main_returns_error_for_invalid_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Возвращает код 1, если переданный путь не является папкой."""
    invalid_path = tmp_path / "not_a_folder.txt"
    invalid_path.write_text("x", encoding="utf-8")
    log_path = tmp_path / "test.log"

    monkeypatch.setattr(sys, "argv", ["file_deduper.py", str(invalid_path)])
    monkeypatch.setattr(file_deduper, "build_log_path", lambda: log_path)

    assert file_deduper.main() == 1
