"""Консольная утилита для поиска файлов с одинаковым содержимым.

Скрипт рекурсивно обходит указанную папку, считает SHA-256 для каждого
обычного файла и выводит группы файлов, у которых совпадает контрольная
сумма. Внутри каждой группы файлы сортируются по имени и выводятся в
формате "имя файла | размер | папка". Результат записывается одновременно в
консоль и в log-файл.
"""

from __future__ import annotations

import argparse
import logging
from collections import defaultdict
from pathlib import Path

from file_utils import (
    build_log_path,
    calculate_checksum,
    configure_logger,
    format_size,
    iter_files,
)

LOGGER_NAME = "file_deduper"


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
    logger = configure_logger(LOGGER_NAME, log_path)

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
