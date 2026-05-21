"""Общие утилиты для консольных скриптов работы с файлами."""

from __future__ import annotations

import hashlib
import logging
import re
import sys
from argparse import ArgumentTypeError
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

BLOCK_SIZE = 1024 * 1024


def build_log_path(prefix: str = "exec") -> Path:
    """Создает папку logs и возвращает путь к новому log-файлу."""
    logs_dir = Path.cwd() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y_%m_%d-%H_%M_%S")
    return logs_dir / f"{prefix}-{timestamp}.log"


def configure_logger(logger_name: str, log_path: Path) -> logging.Logger:
    """Настраивает логгер для вывода сообщений в консоль и log-файл."""
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter("%(message)s")

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def iter_files(
    folder: Path, skip_dir_name_pattern: re.Pattern[str] | None = None
) -> Iterable[Path]:
    """Возвращает все обычные файлы в папке и ее подпапках."""
    for root, dir_names, file_names in folder.walk():
        if skip_dir_name_pattern is not None:
            dir_names[:] = [
                dir_name
                for dir_name in dir_names
                if not skip_dir_name_pattern.search(dir_name)
            ]

        for file_name in file_names:
            path = root / file_name
            if path.is_file():
                yield path


def calculate_checksum(file_path: Path) -> str:
    """Считает SHA-256 контрольную сумму содержимого файла."""
    digest = hashlib.sha256()

    with file_path.open("rb") as file:
        for block in iter(lambda: file.read(BLOCK_SIZE), b""):
            digest.update(block)

    return digest.hexdigest()


def format_size(size_bytes: int) -> str:
    """Форматирует размер файла в человекоудобный вид."""
    units = ("B", "KB", "MB", "GB", "TB")
    size = float(size_bytes)

    for unit in units[:-1]:
        if size < 1024:
            if unit == "B":
                return f"{size_bytes} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024

    return f"{size:.1f} {units[-1]}"


def compile_skip_dir_name_regex(value: str) -> re.Pattern[str]:
    """Компилирует regex для имен папок, которые нужно пропустить."""
    try:
        return re.compile(value)
    except re.error as error:
        raise ArgumentTypeError(
            f"Некорректное регулярное выражение: {error}"
        ) from error
