"""Консольная утилита для сравнения содержимого двух папок.

Скрипт рекурсивно обходит две переданные папки, считает SHA-256 для каждого
обычного файла и сравнивает деревья по контрольной сумме, относительному пути
и имени файла. Размер файла не участвует в сравнении и выводится только для
справки. Результат записывается одновременно в консоль и в log-файл.
"""

from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections import Counter, defaultdict
from dataclasses import dataclass
from logging import Logger
from pathlib import Path
from re import Pattern

from file_utils import (
    build_log_path,
    calculate_checksum,
    compile_skip_dir_name_regex,
    configure_logger,
    format_size,
    iter_files,
)

LOGGER_NAME = "folder_compare"


@dataclass(frozen=True)
class FileRecord:
    """Описывает файл относительно сравниваемой корневой папки."""

    checksum: str
    size: int
    relative_path: str
    name: str

    @property
    def identity(self) -> tuple[str, str]:
        """Возвращает ключ полного совпадения файла."""
        return self.checksum, self.relative_path


def parse_args() -> Namespace:
    """Разбирает аргументы командной строки."""
    parser = ArgumentParser(description="Сравнивает содержимое двух папок по SHA-256.")
    parser.add_argument(
        "first_folder",
        type=Path,
        help="Путь к первой папке.",
    )
    parser.add_argument(
        "second_folder",
        type=Path,
        help="Путь ко второй папке.",
    )
    parser.add_argument(
        "--skip-dir-name-regex",
        type=compile_skip_dir_name_regex,
        default=None,
        help="Регулярное выражение для имени папки, пропускаемой при обходе.",
    )
    return parser.parse_args()


def build_file_record(root: Path, file_path: Path) -> FileRecord:
    """Создает запись о файле относительно корневой папки."""
    relative_path = file_path.relative_to(root)
    checksum = calculate_checksum(file_path)
    size = file_path.stat().st_size

    return FileRecord(
        checksum=checksum,
        size=size,
        relative_path=str(relative_path),
        name=file_path.name,
    )


def index_folder(
    folder: Path,
    logger: Logger,
    skip_dir_name_pattern: Pattern[str] | None = None,
) -> tuple[list[FileRecord], bool]:
    """Собирает записи о файлах в папке.

    Возвращает список записей и признак того, что при чтении были ошибки.
    """
    records: list[FileRecord] = []
    had_read_errors = False

    for file_path in iter_files(folder, skip_dir_name_pattern):
        try:
            records.append(build_file_record(folder, file_path))
        except OSError as error:
            logger.warning("Не удалось прочитать файл %s: %s", file_path, error)
            had_read_errors = True

    return records, had_read_errors


def identity_counter(records: list[FileRecord]) -> Counter[tuple[str, str]]:
    """Считает файлы по ключу полного совпадения."""
    return Counter(record.identity for record in records)


def records_with_common_hash_metadata_diff(
    first_records: list[FileRecord], second_records: list[FileRecord]
) -> tuple[list[FileRecord], list[FileRecord]]:
    """Возвращает файлы с общим хэшем, но без полного совпадения пути/имени."""
    first_hashes = {record.checksum for record in first_records}
    second_hashes = {record.checksum for record in second_records}
    common_hashes = first_hashes & second_hashes

    first_counter = identity_counter(first_records)
    second_counter = identity_counter(second_records)

    first_diff: list[FileRecord] = []
    second_diff: list[FileRecord] = []

    # Сопоставляем файлы с одинаковым (hash, path) как элементы мультимножеств:
    # совпавшие пары «погашаются», остаток попадает в diff соответствующей стороны.
    for record in first_records:
        if record.checksum in common_hashes and second_counter[record.identity] <= 0:
            first_diff.append(record)
        elif record.checksum in common_hashes:
            second_counter[record.identity] -= 1

    for record in second_records:
        if record.checksum in common_hashes and first_counter[record.identity] <= 0:
            second_diff.append(record)
        elif record.checksum in common_hashes:
            first_counter[record.identity] -= 1

    return first_diff, second_diff


def records_with_unique_hashes(
    records: list[FileRecord], other_records: list[FileRecord]
) -> list[FileRecord]:
    """Возвращает файлы, SHA-256 которых нет в другой папке."""
    other_hashes = {record.checksum for record in other_records}
    return [record for record in records if record.checksum not in other_hashes]


def sort_by_hash_name_path(record: FileRecord) -> tuple[str, str, str]:
    """Ключ сортировки для различий при совпадающем содержимом."""
    return record.checksum, record.name.casefold(), record.relative_path.casefold()


def sort_by_path_name(record: FileRecord) -> tuple[str, str]:
    """Ключ сортировки для файлов, найденных только в одной папке."""
    return record.relative_path.casefold(), record.name.casefold()


def log_record(record: FileRecord, logger: Logger, indent: str = "  ") -> None:
    """Выводит одну запись о файле."""
    logger.info(
        "%s%s | %s | %s",
        indent,
        record.name,
        format_size(record.size),
        record.relative_path,
    )


def log_metadata_differences(
    first_records: list[FileRecord],
    second_records: list[FileRecord],
    first_folder: Path,
    second_folder: Path,
    logger: Logger,
) -> None:
    """Выводит различия путей и имен для файлов с совпадающим SHA-256."""
    if not first_records and not second_records:
        return

    logger.info("")
    logger.info("Файлы с одинаковым содержимым, но отличающимися именами или путями:")

    grouped: dict[str, dict[str, list[FileRecord]]] = defaultdict(
        lambda: {"first": [], "second": []}
    )
    for record in first_records:
        grouped[record.checksum]["first"].append(record)
    for record in second_records:
        grouped[record.checksum]["second"].append(record)

    for checksum in sorted(grouped):
        logger.info("")
        logger.info("Контрольная сумма: %s", checksum)

        first_group = sorted(grouped[checksum]["first"], key=sort_by_hash_name_path)
        second_group = sorted(grouped[checksum]["second"], key=sort_by_hash_name_path)

        if first_group:
            logger.info("  %s:", first_folder)
            for record in first_group:
                log_record(record, logger, indent="    ")

        if second_group:
            logger.info("  %s:", second_folder)
            for record in second_group:
                log_record(record, logger, indent="    ")


def log_unique_hash_records(
    title: str, records: list[FileRecord], logger: Logger
) -> None:
    """Выводит файлы, SHA-256 которых нет в другой папке."""
    if not records:
        return

    logger.info("")
    logger.info(title)
    for record in sorted(records, key=sort_by_path_name):
        log_record(record, logger)


def log_comparison_result(
    first_records: list[FileRecord],
    second_records: list[FileRecord],
    first_folder: Path,
    second_folder: Path,
    logger: Logger,
    log_path: Path,
) -> None:
    """Выводит результат сравнения двух папок."""
    if identity_counter(first_records) == identity_counter(second_records):
        logger.info("Содержимое папок полностью совпадает.")
        logger.info("Log-файл: %s", log_path.resolve())
        return

    metadata_first, metadata_second = records_with_common_hash_metadata_diff(
        first_records, second_records
    )
    unique_first = records_with_unique_hashes(first_records, second_records)
    unique_second = records_with_unique_hashes(second_records, first_records)

    logger.info("Содержимое папок отличается.")
    log_metadata_differences(
        metadata_first, metadata_second, first_folder, second_folder, logger
    )
    log_unique_hash_records(
        f'Файлы, которые есть только в папке "{first_folder}":',
        unique_first,
        logger,
    )
    log_unique_hash_records(
        f'Файлы, которые есть только в папке "{second_folder}":',
        unique_second,
        logger,
    )
    logger.info("")
    logger.info("Log-файл: %s", log_path.resolve())


def main() -> int:
    """Запускает сравнение двух папок и возвращает код завершения."""
    args = parse_args()
    first_folder = args.first_folder.expanduser().resolve()
    second_folder = args.second_folder.expanduser().resolve()
    log_path = build_log_path(prefix="compare")
    logger = configure_logger(LOGGER_NAME, log_path)

    has_invalid_folder = False
    if not first_folder.is_dir():
        logger.error('Путь к папке "%s" не является папкой', first_folder)
        has_invalid_folder = True
    if not second_folder.is_dir():
        logger.error('Путь к папке "%s" не является папкой', second_folder)
        has_invalid_folder = True
    if has_invalid_folder:
        logger.info("Log-файл: %s", log_path.resolve())
        return 1

    logger.info("%s", first_folder)
    logger.info("%s", second_folder)
    logger.info("Начинаю сравнение папок...")
    first_records, first_had_read_errors = index_folder(
        first_folder, logger, args.skip_dir_name_regex
    )
    second_records, second_had_read_errors = index_folder(
        second_folder, logger, args.skip_dir_name_regex
    )

    if first_had_read_errors or second_had_read_errors:
        logger.error("Сравнение остановлено из-за ошибок чтения файлов.")
        logger.info("Log-файл: %s", log_path.resolve())
        return 1

    log_comparison_result(
        first_records, second_records, first_folder, second_folder, logger, log_path
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
