"""Turns messy cell values into dates, amounts and known products.

No row disappears silently: each one ends up in the report, the problem list or a named counter.
Money is kept in whole grosze, so totals stay exact to the grosz.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .config import CANCELLED, RETURN, ConfigError, Source
from .readers import RawRow

KIND_ERROR = "błąd"
KIND_WARNING = "ostrzeżenie"
KIND_DUPLICATE = "duplikat"
UNASSIGNED_CATEGORY = "Nieprzypisane"

_DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%d.%m.%Y %H:%M",
    "%d.%m.%Y",
    "%d-%m-%Y",
)
_POLISH_MONTHS = {
    "sty": 1, "lut": 2, "mar": 3, "kwi": 4, "maj": 5, "cze": 6,
    "lip": 7, "sie": 8, "wrz": 9, "paź": 10, "paz": 10, "lis": 11, "gru": 12,
}
_POLISH_DATE = re.compile(r"^(\d{1,2})\s+(\w{3})\w*\.?\s+(\d{4})$")
_EXCEL_EPOCH = date(1899, 12, 30)


def parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # A date cell Excel exported as a bare serial number. Other numbers are not dates.
        return _EXCEL_EPOCH + timedelta(days=int(value)) if 30000 <= value <= 60000 else None
    if not isinstance(value, str):
        return None

    text = value.strip()
    for pattern in _DATE_FORMATS:
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue

    match = _POLISH_DATE.match(text.casefold())
    if match and match.group(2) in _POLISH_MONTHS:
        try:
            return date(int(match.group(3)), _POLISH_MONTHS[match.group(2)], int(match.group(1)))
        except ValueError:
            return None
    return None


def parse_amount(value: Any) -> Decimal | None:
    """Reads amounts like 59,90 / 1 234,50 zł / 1.234,50 / 1,234.50 / 59.9.

    A value such as 12,345 is rejected instead of guessed, because it could mean 12.35 or 12345.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return None if value != value else Decimal(str(value))

    text = re.sub(r"(?i)(zł|zl|pln)\.?", "", str(value))
    text = re.sub(r"[\s  ]", "", text)
    if not re.fullmatch(r"-?\d[\d.,]*", text):
        return None

    comma, dot = text.rfind(","), text.rfind(".")
    if comma >= 0 and dot >= 0:
        decimal_mark, thousands_mark = (",", ".") if comma > dot else (".", ",")
        whole, _, fraction = text.rpartition(decimal_mark)
        whole = whole.replace(thousands_mark, "")
        if not whole.lstrip("-").isdigit() or not fraction.isdigit() or len(fraction) > 2:
            return None
        text = f"{whole}.{fraction}"
    elif comma >= 0 or dot >= 0:
        mark = "," if comma >= 0 else "."
        parts = text.split(mark)
        if len(parts) > 2:
            if not all(len(part) == 3 for part in parts[1:]):
                return None
            text = "".join(parts)
        elif not parts[1] or len(parts[1]) > 2:
            return None
        else:
            text = ".".join(parts)

    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def to_grosze(amount: Decimal) -> int:
    return int((amount * 100).to_integral_value(rounding=ROUND_HALF_UP))


def parse_quantity(value: Any) -> int | None:
    """Reads a positive whole quantity, for example 2, 2.0, "2 szt." or "2,0"."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = re.sub(r"(?i)\s*(szt|sztuk)\.?\s*$", "", value.strip())
    amount = parse_amount(value)
    if amount is None or amount <= 0 or amount != amount.to_integral_value():
        return None
    return int(amount)


def normalize_name(text: str) -> str:
    """Key for comparing product names, ignoring case, extra spaces and "450 ml" versus "450ml"."""
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"(\d)\s*(ml|l|kg|g|cm|szt)\b", r"\1\2", text)


@dataclass(frozen=True)
class Product:
    name: str
    category: str


class Catalog:
    """Product list with the aliases each sales channel uses for the same item."""

    def __init__(self, products: dict[str, Product]):
        self._products = products

    @classmethod
    def load(cls, path: Path) -> "Catalog":
        if not path.exists():
            raise ConfigError(f"Nie znaleziono listy produktów: {path}")
        products: dict[str, Product] = {}
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=";")
            missing = {"nazwa", "kategoria"} - set(reader.fieldnames or [])
            if missing:
                raise ConfigError(f"W pliku {path.name} brakuje kolumn: {', '.join(sorted(missing))}.")
            for record in reader:
                product = Product(record["nazwa"].strip(), record["kategoria"].strip())
                names = [record["nazwa"], *(record.get("aliasy") or "").split("|")]
                for name in filter(None, (normalize_name(item) for item in names)):
                    products[name] = product
        return cls(products)

    def match(self, name: str) -> Product | None:
        return self._products.get(normalize_name(name))


@dataclass(frozen=True)
class Problem:
    source: str
    line: int
    kind: str
    reason: str
    raw: str


@dataclass(frozen=True)
class CleanRow:
    source: str
    number: str
    day: date
    product: str
    category: str
    quantity: int
    price_gr: int
    value_gr: int
    is_return: bool


@dataclass
class SourceStats:
    """Row counts for one source. The check below must always hold."""

    name: str
    file: str = ""
    read: int = 0
    in_report: int = 0
    cancelled: int = 0
    duplicates: int = 0
    errors: int = 0
    skipped: int = 0
    out_of_period: int = 0
    warnings: int = 0
    value_gr: int = 0
    declared_total_gr: int | None = None

    @property
    def balanced(self) -> bool:
        accounted = (
            self.in_report + self.cancelled + self.duplicates + self.errors + self.skipped + self.out_of_period
        )
        return self.read == accounted

    @property
    def total_difference_gr(self) -> int | None:
        return None if self.declared_total_gr is None else self.declared_total_gr - self.value_gr


@dataclass
class SourceResult:
    stats: SourceStats
    rows: list[CleanRow] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)


def _describe_raw(values: dict[str, Any]) -> str:
    return " | ".join("" if value is None else str(value) for value in values.values())


def clean_source(
    source: Source,
    raw_rows: list[RawRow],
    catalog: Catalog,
    date_from: date | None = None,
    date_to: date | None = None,
) -> SourceResult:
    result = SourceResult(SourceStats(source.name, source.file))
    stats = result.stats
    seen: set[tuple] = set()
    period_filtered = date_from is not None or date_to is not None

    def report(row: RawRow, kind: str, reason: str) -> None:
        result.problems.append(Problem(source.name, row.line, kind, reason, _describe_raw(row.values)))

    for row in raw_rows:
        stats.read += 1
        values = row.values

        if all(value is None for value in values.values()):
            stats.skipped += 1
            continue

        number = values["numer"]
        if source.total_marker and str(number).casefold() == source.total_marker.casefold():
            stats.skipped += 1
            declared = parse_amount(row.total)
            if declared is not None and not period_filtered:
                stats.declared_total_gr = to_grosze(declared)
            continue

        kind = "sprzedaz"
        if "status" in source.columns:
            status = str(values.get("status") or "").casefold()
            kind = source.statuses.get(status)
            if kind is None:
                stats.errors += 1
                report(row, KIND_ERROR, f"Nieznany status: „{values.get('status') or 'pusty'}”.")
                continue
            if kind == CANCELLED:
                stats.cancelled += 1
                continue

        day = parse_date(values["data"])
        quantity = parse_quantity(values["ilosc"])
        price = parse_amount(values["cena"])
        product_name = values["produkt"]

        reasons = []
        if day is None:
            reasons.append(f"Nieczytelna data: „{values['data'] if values['data'] is not None else 'pusta'}”.")
        if not product_name:
            reasons.append("Brak nazwy produktu.")
        if quantity is None:
            reasons.append(f"Niepoprawna ilość: „{values['ilosc'] if values['ilosc'] is not None else 'pusta'}”.")
        if price is None or price <= 0:
            reasons.append(f"Niepoprawna cena: „{values['cena'] if values['cena'] is not None else 'pusta'}”.")
        if reasons:
            stats.errors += 1
            report(row, KIND_ERROR, " ".join(reasons))
            continue

        price_gr = to_grosze(price)
        product_name = str(product_name)

        if source.detect_duplicates:
            key = (str(number), day, normalize_name(product_name), quantity, price_gr, kind)
            if key in seen:
                stats.duplicates += 1
                report(row, KIND_DUPLICATE, f"Ten sam wiersz co wcześniej dla numeru {number}. Policzono raz.")
                continue
            seen.add(key)

        if (date_from and day < date_from) or (date_to and day > date_to):
            stats.out_of_period += 1
            continue

        product = catalog.match(product_name)
        if product is None:
            stats.warnings += 1
            report(row, KIND_WARNING, f"Produktu „{product_name}” nie ma na liście. Policzono jako nieprzypisany.")
            product = Product(re.sub(r"\s+", " ", product_name).strip(), UNASSIGNED_CATEGORY)

        is_return = kind == RETURN
        value_gr = price_gr * quantity * (-1 if is_return else 1)
        result.rows.append(
            CleanRow(
                source=source.name,
                number=str(number) if number is not None else "",
                day=day,
                product=product.name,
                category=product.category,
                quantity=-quantity if is_return else quantity,
                price_gr=price_gr,
                value_gr=value_gr,
                is_return=is_return,
            )
        )
        stats.in_report += 1
        stats.value_gr += value_gr

    return result
