"""Reads config.toml and turns mistakes in it into messages a non-programmer can act on."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

REQUIRED_COLUMNS = ("numer", "data", "produkt", "ilosc", "cena")
SALE = "sprzedaz"
CANCELLED = "anulowane"
RETURN = "zwrot"


class ConfigError(Exception):
    """A problem the user can fix in the configuration or the input files."""


@dataclass(frozen=True)
class Source:
    name: str
    file: str
    columns: dict[str, str]
    separator: str = ","
    encoding: str = "utf-8-sig"
    sheet: str | None = None
    header_row: int = 1
    statuses: dict[str, str] = field(default_factory=dict)
    detect_duplicates: bool = True
    total_marker: str | None = None
    total_column: str | None = None


@dataclass(frozen=True)
class Config:
    company: str
    products_file: str
    sources: tuple[Source, ...]
    note: str | None = None


def _parse_source(raw: dict) -> Source:
    name = raw.get("nazwa") or raw.get("plik") or "bez nazwy"
    for key in ("nazwa", "plik", "kolumny"):
        if key not in raw:
            raise ConfigError(f"W źródle „{name}” brakuje pola „{key}”.")

    columns = raw["kolumny"]
    missing = [key for key in REQUIRED_COLUMNS if key not in columns]
    if missing:
        raise ConfigError(f"W źródle „{name}” brakuje opisu kolumn: {', '.join(missing)}.")

    statuses = {str(key).casefold(): value for key, value in raw.get("statusy", {}).items()}
    unknown = sorted(set(statuses.values()) - {SALE, CANCELLED, RETURN})
    if unknown:
        raise ConfigError(
            f"W źródle „{name}” status może oznaczać tylko: {SALE}, {CANCELLED} lub {RETURN}. "
            f"Znaleziono: {', '.join(unknown)}."
        )
    if "status" in columns and not statuses:
        raise ConfigError(f"Źródło „{name}” ma kolumnę statusu, ale brakuje sekcji statusy.")

    return Source(
        name=raw["nazwa"],
        file=raw["plik"],
        columns=dict(columns),
        separator=raw.get("separator", ","),
        encoding=raw.get("kodowanie", "utf-8-sig"),
        sheet=raw.get("arkusz"),
        header_row=int(raw.get("wiersz_naglowka", 1)),
        statuses=statuses,
        detect_duplicates=bool(raw.get("wykrywaj_duplikaty", True)),
        total_marker=raw.get("znacznik_sumy"),
        total_column=raw.get("kolumna_sumy"),
    )


def load_config(path: Path) -> Config:
    if not path.exists():
        raise ConfigError(f"Nie znaleziono pliku konfiguracji: {path}")
    try:
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"Plik {path.name} ma błąd składni: {error}") from error

    sources = raw.get("zrodla", [])
    if not sources:
        raise ConfigError(f"W pliku {path.name} nie ma żadnego bloku [[zrodla]].")

    report = raw.get("raport", {})
    return Config(
        company=report.get("firma", "Raport sprzedaży"),
        products_file=report.get("produkty", "produkty.csv"),
        sources=tuple(_parse_source(source) for source in sources),
        note=report.get("uwaga"),
    )
