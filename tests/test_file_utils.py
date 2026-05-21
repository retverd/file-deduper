"""Тесты общих утилит."""

import re
from argparse import ArgumentTypeError
from pathlib import Path

import pytest

from file_utils import compile_skip_dir_name_regex, format_size, iter_files


@pytest.mark.parametrize(
    ("size_bytes", "expected"),
    [
        (0, "0 B"),
        (512, "512 B"),
        (1024, "1.0 KB"),
        (1536, "1.5 KB"),
        (1024**3, "1.0 GB"),
    ],
)
def test_format_size(size_bytes: int, expected: str) -> None:
    """Проверяет форматирование размера в байтах, KB, MB и GB."""
    assert format_size(size_bytes) == expected


def test_compile_skip_dir_name_regex_valid() -> None:
    """Компилирует корректное выражение и проверяет совпадение по имени папки."""
    pattern = compile_skip_dir_name_regex(r"^\.git$")
    assert pattern.search(".git")
    assert pattern.search(".github") is None


def test_compile_skip_dir_name_regex_invalid() -> None:
    """При синтаксической ошибке regex выбрасывает ArgumentTypeError."""
    with pytest.raises(ArgumentTypeError, match="Некорректное регулярное выражение"):
        compile_skip_dir_name_regex("[invalid")


def test_iter_files_skips_matching_directory_names(tmp_path: Path) -> None:
    """Не обходит подпапки, имя которых совпадает с skip-dir-name-regex."""
    (tmp_path / "keep.txt").write_text("a", encoding="utf-8")
    skipped_dir = tmp_path / "node_modules"
    skipped_dir.mkdir()
    (skipped_dir / "skip.txt").write_text("b", encoding="utf-8")
    visible_dir = tmp_path / "src"
    visible_dir.mkdir()
    (visible_dir / "nested.txt").write_text("c", encoding="utf-8")

    paths = list(iter_files(tmp_path, re.compile(r"^node_modules$")))

    assert {path.name for path in paths} == {"keep.txt", "nested.txt"}
