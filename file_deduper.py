"""Консольная утилита для поиска файлов с одинаковым содержимым.

Скрипт рекурсивно обходит указанную папку, считает SHA-256 для каждого
обычного файла и выводит группы файлов, у которых совпадает контрольная
сумма. Внутри каждой группы файлы сортируются по имени и выводятся в
формате "имя файла | размер | папка". Результат записывается одновременно в
консоль и в log-файл.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable

BLOCK_SIZE = 1024 * 1024
LOGGER_NAME = "file_deduper"


def build_log_path() -> Path:
    """Создает папку logs и возвращает путь к новому log-файлу.

    Имя файла содержит timestamp с подчеркиваниями между группами даты и
    времени: exec-YYYY_MM_DD-HH_MM_SS.log.
    """
    logs_dir = Path.cwd() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y_%m_%d-%H_%M_%S")
    return logs_dir / f"exec-{timestamp}.log"


def configure_logger(log_path: Path) -> logging.Logger:
    """Настраивает логгер для вывода сообщений в консоль и log-файл."""
    logger = logging.getLogger(LOGGER_NAME)
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


def parse_args() -> argparse.Namespace:
    """Разбирает аргументы командной строки."""
    parser = argparse.ArgumentParser(
        description="Находит файлы с одинаковым содержимым по SHA-256."
    )
    parser.add_argument(
        "folder",
        type=Path,
        help="Путь к папке, которую нужно проверить.",
    )
    return parser.parse_args()


def iter_files(folder: Path) -> Iterable[Path]:
    """Возвращает все обычные файлы в папке и ее подпапках."""
    for path in folder.rglob("*"):
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

    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{size_bytes} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024

    return f"{size_bytes} B"


def find_duplicates(folder: Path, logger: logging.Logger) -> dict[str, list[Path]]:
    """Находит группы файлов с одинаковыми контрольными суммами.

    Возвращает словарь, где ключом является SHA-256, а значением - список
    абсолютных путей к файлам с такой контрольной суммой.
    """
    checksums: dict[str, list[Path]] = defaultdict(list)

    for file_path in iter_files(folder):
        try:
            checksum = calculate_checksum(file_path)
        except OSError as error:
            logger.warning("Не удалось прочитать файл %s: %s", file_path, error)
            continue

        checksums[checksum].append(file_path.resolve())

    return {checksum: paths for checksum, paths in checksums.items() if len(paths) > 1}


def log_duplicates(
    duplicates: dict[str, list[Path]], logger: logging.Logger, log_path: Path
) -> None:
    """Выводит группы дубликатов в формате ``имя файла | размер | папка``.

    Внутри каждой группы файлы сортируются по имени, затем по папке, чтобы
    одинаковые имена располагались рядом.
    """
    if not duplicates:
        logger.info("Дубликаты не найдены.")
        logger.info("Log-файл: %s", log_path.resolve())
        return

    logger.info("Найдены файлы с одинаковым содержимым:")
    reclaimable_bytes = 0

    for checksum, paths in sorted(duplicates.items()):
        logger.info("")
        logger.info("Контрольная сумма: %s", checksum)
        file_size = paths[0].stat().st_size
        reclaimable_bytes += file_size * (len(paths) - 1)
        for path in sorted(
            paths,
            key=lambda path: (
                path.name.casefold(),
                str(path.parent).casefold(),
            ),
        ):
            logger.info(
                "  %s | %s | %s",
                path.name,
                format_size(path.stat().st_size),
                path.parent,
            )

    logger.info("")
    logger.info("Можно освободить до %s места!", format_size(reclaimable_bytes))
    logger.info("Log-файл: %s", log_path.resolve())


def main() -> int:
    """Запускает проверку указанной папки и возвращает код завершения."""
    args = parse_args()
    folder = args.folder.expanduser().resolve()
    log_path = build_log_path()
    logger = configure_logger(log_path)

    logger.info("%s", folder)

    if not folder.is_dir():
        logger.error("Указанный путь не является папкой: %s", folder)
        logger.info("Log-файл: %s", log_path.resolve())
        return 1

    logger.info("Начинаю проверку папки...")
    duplicates = find_duplicates(folder, logger)
    log_duplicates(duplicates, logger, log_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
