"""Polish formatting shared by the Excel and HTML reports."""

from __future__ import annotations

from datetime import date

NBSP = " "
MONTH_NAMES = (
    "styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec",
    "lipiec", "sierpień", "wrzesień", "październik", "listopad", "grudzień",
)


def group_digits(number: int) -> str:
    """Groups thousands the Polish way: from five digits up, so 1234 but 12 345."""
    sign = "-" if number < 0 else ""
    digits = str(abs(number))
    if len(digits) < 5:
        return f"{sign}{digits}"
    return sign + f"{int(digits):,}".replace(",", NBSP)


def format_pln(grosze: int) -> str:
    sign = "-" if grosze < 0 else ""
    whole, fraction = divmod(abs(grosze), 100)
    return f"{sign}{group_digits(whole)},{fraction:02d}{NBSP}zł"


def format_month(month: str) -> str:
    year, number = month.split("-")
    return f"{MONTH_NAMES[int(number) - 1]} {year}"


def format_day(day: date) -> str:
    return day.strftime("%d.%m.%Y")


def plural(count: int, one: str, few: str, many: str) -> str:
    if count == 1:
        return one
    last_digit, last_two = count % 10, count % 100
    return few if 2 <= last_digit <= 4 and not 12 <= last_two <= 14 else many
