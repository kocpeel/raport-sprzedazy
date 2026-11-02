"""Reads source files row by row, keeping each row's real line number for the problem list."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from .config import ConfigError, Source

EXCEL_SUFFIXES = {".xlsx", ".xlsm"}


@dataclass(frozen=True)
class RawRow:
    line: int
    values: dict[str, Any]
    total: Any = None


def _clean_header(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _blank_to_none(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _check_columns(source: Source, headers: list[str], path: Path) -> None:
    wanted = list(source.columns.values())
    if source.total_column:
        wanted.append(source.total_column)
    missing = [column for column in wanted if column not in headers]
    if missing:
        found = ", ".join(header for header in headers if header) or "brak"
        raise ConfigError(
            f"W pliku {path.name} brakuje kolumn: {', '.join(missing)}. Znalezione kolumny: {found}."
        )


def _to_row(source: Source, line: int, record: dict[str, Any]) -> RawRow:
    return RawRow(
        line=line,
        values={key: _blank_to_none(record.get(column)) for key, column in source.columns.items()},
        total=_blank_to_none(record.get(source.total_column)) if source.total_column else None,
    )


def _read_csv(source: Source, path: Path) -> list[RawRow]:
    try:
        with path.open("r", encoding=source.encoding, newline="") as handle:
            reader = csv.DictReader(handle, delimiter=source.separator)
            headers = [_clean_header(name) for name in (reader.fieldnames or [])]
            reader.fieldnames = headers
            _check_columns(source, headers, path)
            return [_to_row(source, reader.line_num, record) for record in reader]
    except UnicodeDecodeError as error:
        raise ConfigError(
            f"Nie mogę odczytać pliku {path.name} kodowaniem {source.encoding}. "
            "Sprawdź pole kodowanie w konfiguracji."
        ) from error


def _read_excel(source: Source, path: Path) -> list[RawRow]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if source.sheet and source.sheet not in workbook.sheetnames:
            raise ConfigError(
                f"W pliku {path.name} nie ma arkusza „{source.sheet}”. "
                f"Arkusze: {', '.join(workbook.sheetnames)}."
            )
        sheet = workbook[source.sheet] if source.sheet else workbook[workbook.sheetnames[0]]
        rows = sheet.iter_rows(min_row=source.header_row, values_only=True)
        headers = [_clean_header(value) for value in next(rows, ())]
        _check_columns(source, headers, path)
        return [
            _to_row(source, source.header_row + 1 + offset, dict(zip(headers, values)))
            for offset, values in enumerate(rows)
        ]
    finally:
        workbook.close()


def read_source(source: Source, data_dir: Path) -> list[RawRow]:
    path = data_dir / source.file
    if not path.exists():
        raise ConfigError(f"Nie znaleziono pliku źródła „{source.name}”: {path}")
    if path.suffix.lower() in EXCEL_SUFFIXES:
        return _read_excel(source, path)
    return _read_csv(source, path)
