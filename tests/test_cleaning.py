from datetime import date, datetime
from decimal import Decimal

import pytest

from raport.cleaning import (
    Catalog,
    Product,
    clean_source,
    normalize_name,
    parse_amount,
    parse_date,
    parse_quantity,
    to_grosze,
)
from raport.config import Source
from raport.readers import RawRow


@pytest.mark.parametrize(
    "text, expected",
    [
        ("59,90", "59.90"),
        ("59.9", "59.9"),
        ("1 234,50 zł", "1234.50"),
        ("1 234,50", "1234.50"),
        ("1.234,50", "1234.50"),
        ("1,234.50", "1234.50"),
        ("1.234.567", "1234567"),
        ("450", "450"),
        ("450 PLN", "450"),
        (59.9, "59.9"),
        (12, "12"),
    ],
)
def test_parse_amount_reads_common_formats(text, expected):
    assert parse_amount(text) == Decimal(expected)


@pytest.mark.parametrize("text", ["", "abc", "12,345", "12.345", "1,2,3", "zł", None, True, "1.234,567"])
def test_parse_amount_rejects_instead_of_guessing(text):
    assert parse_amount(text) is None


def test_to_grosze_avoids_floating_point_errors():
    assert to_grosze(Decimal("19.99")) == 1999
    assert to_grosze(parse_amount(0.1)) + to_grosze(parse_amount(0.2)) == 30
    assert to_grosze(Decimal("10.005")) == 1001


@pytest.mark.parametrize(
    "value, expected",
    [
        ("2026-03-01 14:22", date(2026, 3, 1)),
        ("2026-03-01", date(2026, 3, 1)),
        ("01.03.2026", date(2026, 3, 1)),
        ("5 mar 2026", date(2026, 3, 5)),
        ("5 paź 2026", date(2026, 10, 5)),
        ("5 marca 2026", date(2026, 3, 5)),
        (datetime(2026, 3, 1, 12, 0), date(2026, 3, 1)),
        (date(2026, 3, 1), date(2026, 3, 1)),
        (46082, date(2026, 3, 1)),
    ],
)
def test_parse_date_reads_common_formats(value, expected):
    assert parse_date(value) == expected


@pytest.mark.parametrize("value", ["31.02.2026", "brak daty", "??.??.2026", "", None, 12, "45 mar 2026", "5 xyz 2026"])
def test_parse_date_rejects_impossible_dates(value):
    assert parse_date(value) is None


@pytest.mark.parametrize("value, expected", [(2, 2), ("2", 2), ("2 szt.", 2), ("2,0", 2), (2.0, 2)])
def test_parse_quantity_reads_whole_numbers(value, expected):
    assert parse_quantity(value) == expected


@pytest.mark.parametrize("value", [0, -1, "dużo", "1,5", None, ""])
def test_parse_quantity_rejects_everything_else(value):
    assert parse_quantity(value) is None


def test_normalize_name_ignores_case_spaces_and_units():
    assert normalize_name("  KUBEK  termiczny 450 ML ") == normalize_name("Kubek termiczny 450ml")
    assert normalize_name("ŁÓDKA") == normalize_name("łódka")


CATALOG = Catalog({normalize_name("Kubek 450 ml"): Product("Kubek 450 ml", "Kuchnia")})

SOURCE = Source(
    name="Test",
    file="test.csv",
    columns={"numer": "n", "data": "d", "produkt": "p", "ilosc": "i", "cena": "c", "status": "s"},
    statuses={"ok": "sprzedaz", "anul": "anulowane", "zwrot": "zwrot"},
)


def raw(line, number="A1", day="2026-03-01", product="Kubek 450ml", quantity="1", price="10,00", status="ok"):
    return RawRow(
        line,
        {"numer": number, "data": day, "produkt": product, "ilosc": quantity, "cena": price, "status": status},
    )


def test_clean_row_is_counted_and_matched_to_the_product_list():
    result = clean_source(SOURCE, [raw(2, quantity="3", price="19,99")], CATALOG)
    row = result.rows[0]
    assert (row.product, row.category, row.value_gr) == ("Kubek 450 ml", "Kuchnia", 5997)
    assert result.stats.in_report == 1
    assert result.stats.balanced


def test_return_reduces_revenue():
    result = clean_source(SOURCE, [raw(2), raw(3, number="A2", status="zwrot")], CATALOG)
    assert [row.value_gr for row in result.rows] == [1000, -1000]
    assert result.rows[1].quantity == -1
    assert result.stats.value_gr == 0


def test_cancelled_order_is_counted_but_not_in_revenue():
    result = clean_source(SOURCE, [raw(2, status="ANUL")], CATALOG)
    assert result.rows == []
    assert result.stats.cancelled == 1
    assert result.problems == []


def test_repeated_row_counts_once_and_is_reported():
    result = clean_source(SOURCE, [raw(2), raw(3)], CATALOG)
    assert len(result.rows) == 1
    assert result.stats.duplicates == 1
    assert result.problems[0].kind == "duplikat"
    assert result.problems[0].line == 3


def test_duplicate_detection_can_be_switched_off():
    source = Source(**{**SOURCE.__dict__, "detect_duplicates": False})
    result = clean_source(source, [raw(2), raw(3)], CATALOG)
    assert len(result.rows) == 2


def test_bad_row_lists_every_reason_with_its_line_number():
    result = clean_source(SOURCE, [raw(7, day="31.02.2026", quantity="dużo", price="")], CATALOG)
    assert result.rows == []
    problem = result.problems[0]
    assert problem.kind == "błąd"
    assert problem.line == 7
    assert "Nieczytelna data" in problem.reason
    assert "Niepoprawna ilość" in problem.reason
    assert "Niepoprawna cena" in problem.reason


def test_unknown_product_stays_in_revenue_with_a_warning():
    result = clean_source(SOURCE, [raw(2, product="Nowy  termos")], CATALOG)
    assert result.rows[0].category == "Nieprzypisane"
    assert result.rows[0].product == "Nowy termos"
    assert result.rows[0].value_gr == 1000
    assert result.problems[0].kind == "ostrzeżenie"


def test_unknown_status_is_an_error_not_a_sale():
    result = clean_source(SOURCE, [raw(2, status="dziwny")], CATALOG)
    assert result.rows == []
    assert "Nieznany status" in result.problems[0].reason


def test_blank_rows_are_skipped_and_counted():
    blank = RawRow(5, dict.fromkeys(SOURCE.columns))
    result = clean_source(SOURCE, [blank], CATALOG)
    assert result.stats.skipped == 1
    assert result.stats.balanced


def test_period_filter_counts_rows_outside_it():
    rows = [raw(2, number="A1", day="2026-01-15"), raw(3, number="A2", day="2026-03-15")]
    result = clean_source(SOURCE, rows, CATALOG, date(2026, 3, 1), date(2026, 3, 31))
    assert [row.number for row in result.rows] == ["A2"]
    assert result.stats.out_of_period == 1
    assert result.stats.balanced


def test_total_row_is_compared_with_the_rows_kept():
    source = Source(
        name="Kasa",
        file="k.xlsx",
        columns={"numer": "n", "data": "d", "produkt": "p", "ilosc": "i", "cena": "c"},
        total_marker="SUMA",
        total_column="w",
    )
    good = RawRow(2, {"numer": "P1", "data": "2026-03-01", "produkt": "Kubek 450 ml", "ilosc": 1, "cena": 10})
    total = RawRow(3, {"numer": "suma", "data": None, "produkt": None, "ilosc": None, "cena": None}, total=15)
    result = clean_source(source, [good, total], CATALOG)
    assert result.stats.skipped == 1
    assert result.stats.declared_total_gr == 1500
    assert result.stats.total_difference_gr == 500
