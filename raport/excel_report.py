"""Writes the workbook: summary with charts, products, cleaned data, problems and row counts."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.drawing.line import LineProperties
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from .formatting import format_day, format_month
from .pipeline import Report

MONEY = '#,##0.00\\ "zł"'
INTEGER = "#,##0"
PERCENT = "0.0%"
INK = "1F2933"
MUTED = "5F6B76"
HEADER_FILL = PatternFill("solid", fgColor="E8EDF2")
LINE = Side(style="thin", color="CBD3DB")
# Same order and values as the HTML chart. Checked with a colour-blindness validator.
SERIES_COLORS = ("2A78D6", "EB6834", "1BAF7A")

TITLE_FONT = Font(name="Calibri", size=18, bold=True, color=INK)
SECTION_FONT = Font(name="Calibri", size=12, bold=True, color=INK)
MUTED_FONT = Font(name="Calibri", size=10, color=MUTED)
HEADER_FONT = Font(name="Calibri", bold=True, color=INK)
TOTAL_FONT = Font(name="Calibri", bold=True, color=INK)


def _write_header(sheet: Worksheet, row: int, labels: list[str], column: int = 1) -> None:
    for offset, label in enumerate(labels):
        cell = sheet.cell(row=row, column=column + offset, value=label)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.border = Border(bottom=LINE)
        cell.alignment = Alignment(horizontal="left" if offset == 0 else "right", wrap_text=True, vertical="center")


def _set_widths(sheet: Worksheet, widths: list[float]) -> None:
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width


def _write_summary(sheet: Worksheet, report: Report) -> None:
    sheet.sheet_view.showGridLines = False
    _set_widths(sheet, [30, 18, 18, 18, 18, 3, 12, 12, 12, 12, 12, 12])

    sheet["A1"] = f"Raport sprzedaży: {report.company}"
    sheet["A1"].font = TITLE_FONT
    period = f"Okres: {format_day(report.first_day)} – {format_day(report.last_day)}"
    sheet["A2"] = f"{period}. {report.note}" if report.note else period
    sheet["A2"].font = MUTED_FONT

    figures = [
        ("Przychód po zwrotach", report.revenue_gr / 100, MONEY),
        ("Sprzedaż", report.sales_gr / 100, MONEY),
        ("Zwroty", report.returns_gr / 100, MONEY),
        ("Zamówienia", report.orders, INTEGER),
        ("Średnia wartość zamówienia", report.average_order_gr / 100, MONEY),
        ("Sprzedane sztuki po zwrotach", report.units, INTEGER),
    ]
    for offset, (label, value, number_format) in enumerate(figures):
        row = 4 + offset
        sheet.cell(row=row, column=1, value=label)
        cell = sheet.cell(row=row, column=2, value=value)
        cell.number_format = number_format
        cell.font = TOTAL_FONT

    table_row = 11
    sheet.cell(row=table_row, column=1, value="Przychód według miesięcy").font = SECTION_FONT
    header_row = table_row + 1
    _write_header(sheet, header_row, ["Miesiąc", *report.channels, "Razem"])
    for offset, month in enumerate(report.months):
        row = header_row + 1 + offset
        sheet.cell(row=row, column=1, value=format_month(month))
        values = report.month_values[month]
        for column, channel in enumerate(report.channels, start=2):
            sheet.cell(row=row, column=column, value=values[channel] / 100).number_format = MONEY
        total = sheet.cell(row=row, column=2 + len(report.channels), value=sum(values.values()) / 100)
        total.number_format = MONEY
        total.font = TOTAL_FONT

    last_row = header_row + len(report.months)
    total_row = last_row + 1
    label = sheet.cell(row=total_row, column=1, value="Razem")
    label.font = TOTAL_FONT
    label.border = Border(top=LINE)
    for column, channel in enumerate(report.channels, start=2):
        value = sum(report.month_values[month][channel] for month in report.months) / 100
        cell = sheet.cell(row=total_row, column=column, value=value)
        cell.number_format = MONEY
        cell.font = TOTAL_FONT
        cell.border = Border(top=LINE)
    grand = sheet.cell(row=total_row, column=2 + len(report.channels), value=report.revenue_gr / 100)
    grand.number_format = MONEY
    grand.font = TOTAL_FONT
    grand.border = Border(top=LINE)

    chart = BarChart()
    chart.type = "col"
    chart.grouping = "stacked"
    chart.overlap = 100
    chart.gapWidth = 120
    chart.title = "Przychód według miesięcy i kanałów (zł)"
    chart.height = 9
    chart.width = 22
    chart.legend.position = "b"
    chart.y_axis.number_format = "#,##0"
    chart.y_axis.majorGridlines.spPr = GraphicalProperties(ln=LineProperties(solidFill="E1E0D9"))
    chart.y_axis.delete = False
    chart.x_axis.delete = False
    data = Reference(
        sheet,
        min_col=2,
        max_col=1 + len(report.channels),
        min_row=header_row,
        max_row=last_row,
    )
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(Reference(sheet, min_col=1, min_row=header_row + 1, max_row=last_row))
    for series, color in zip(chart.series, SERIES_COLORS):
        series.graphicalProperties.solidFill = color
        series.graphicalProperties.line.solidFill = color
    sheet.add_chart(chart, f"A{total_row + 2}")


def _write_products(sheet: Worksheet, report: Report) -> None:
    sheet.sheet_view.showGridLines = False
    _set_widths(sheet, [34, 18, 16, 12, 12])
    sheet["A1"] = "Produkty według przychodu"
    sheet["A1"].font = TITLE_FONT
    _write_header(sheet, 3, ["Produkt", "Kategoria", "Przychód", "Sztuki", "Udział"])
    sheet.freeze_panes = "A4"

    revenue = report.revenue_gr or 1
    for offset, product in enumerate(report.products.itertuples(index=False)):
        row = 4 + offset
        sheet.cell(row=row, column=1, value=product.product)
        sheet.cell(row=row, column=2, value=product.category)
        sheet.cell(row=row, column=3, value=int(product.value_gr) / 100).number_format = MONEY
        sheet.cell(row=row, column=4, value=int(product.units)).number_format = INTEGER
        sheet.cell(row=row, column=5, value=int(product.value_gr) / revenue).number_format = PERCENT

    shown = min(10, len(report.products))
    chart = BarChart()
    chart.type = "bar"
    chart.gapWidth = 60
    chart.title = f"{shown} najlepszych produktów (zł)"
    chart.height = 10
    chart.width = 20
    chart.legend = None
    chart.y_axis.number_format = "#,##0"
    chart.y_axis.delete = False
    chart.x_axis.delete = False
    chart.x_axis.scaling.orientation = "maxMin"
    chart.add_data(Reference(sheet, min_col=3, min_row=3, max_row=3 + shown), titles_from_data=True)
    chart.set_categories(Reference(sheet, min_col=1, min_row=4, max_row=3 + shown))
    chart.series[0].graphicalProperties.solidFill = SERIES_COLORS[0]
    chart.series[0].graphicalProperties.line.solidFill = SERIES_COLORS[0]
    sheet.add_chart(chart, "G3")


def _write_rows(sheet: Worksheet, report: Report) -> None:
    labels = ["Data", "Kanał", "Numer", "Produkt", "Kategoria", "Ilość", "Cena", "Wartość", "Typ"]
    _write_header(sheet, 1, labels)
    _set_widths(sheet, [12, 20, 16, 34, 16, 8, 12, 12, 10])
    sheet.freeze_panes = "A2"

    for row in report.rows.itertuples(index=False):
        sheet.append(
            [
                row.day,
                row.source,
                row.number,
                row.product,
                row.category,
                int(row.quantity),
                int(row.price_gr) / 100,
                int(row.value_gr) / 100,
                "zwrot" if row.is_return else "sprzedaż",
            ]
        )
    last_row = sheet.max_row
    for row in range(2, last_row + 1):
        sheet.cell(row=row, column=1).number_format = "yyyy-mm-dd"
        sheet.cell(row=row, column=7).number_format = MONEY
        sheet.cell(row=row, column=8).number_format = MONEY
    sheet.auto_filter.ref = f"A1:I{last_row}"


def _write_problems(sheet: Worksheet, report: Report) -> None:
    _write_header(sheet, 1, ["Rodzaj", "Kanał", "Wiersz w pliku", "Powód", "Zawartość wiersza"])
    _set_widths(sheet, [13, 20, 10, 62, 70])
    sheet.freeze_panes = "A2"
    order = {"błąd": 0, "ostrzeżenie": 1, "duplikat": 2}
    problems = sorted(report.problems, key=lambda item: (order[item.kind], item.source, item.line))
    for problem in problems:
        sheet.append([problem.kind, problem.source, problem.line, problem.reason, problem.raw])
    for row in sheet.iter_rows(min_row=2, min_col=4, max_col=5):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    if problems:
        sheet.auto_filter.ref = f"A1:E{sheet.max_row}"


def _write_checks(sheet: Worksheet, report: Report) -> None:
    sheet.sheet_view.showGridLines = False
    _set_widths(sheet, [24, 12, 12, 12, 12, 12, 12, 12, 16, 16, 16])
    sheet["A1"] = "Kontrola: czy każdy wiersz ma swoje miejsce"
    sheet["A1"].font = TITLE_FONT
    sheet["A2"] = "Wczytane = w raporcie + anulowane + duplikaty + błędy + pominięte + poza okresem."
    sheet["A2"].font = MUTED_FONT
    labels = [
        "Kanał", "Wczytane", "W raporcie", "Anulowane", "Duplikaty", "Błędy", "Pominięte", "Poza okresem",
        "Wartość w raporcie", "Suma z pliku", "Różnica",
    ]
    _write_header(sheet, 4, labels)
    sheet.row_dimensions[4].height = 32
    for offset, stats in enumerate(report.sources):
        row = 5 + offset
        counts = [
            stats.read, stats.in_report, stats.cancelled, stats.duplicates,
            stats.errors, stats.skipped, stats.out_of_period,
        ]
        sheet.cell(row=row, column=1, value=stats.name)
        for column, count in enumerate(counts, start=2):
            sheet.cell(row=row, column=column, value=count)
        sheet.cell(row=row, column=9, value=stats.value_gr / 100).number_format = MONEY
        if stats.declared_total_gr is not None:
            sheet.cell(row=row, column=10, value=stats.declared_total_gr / 100).number_format = MONEY
            sheet.cell(row=row, column=11, value=stats.total_difference_gr / 100).number_format = MONEY


def write_excel(report: Report, path: Path) -> None:
    workbook = Workbook()
    summary = workbook.active
    summary.title = "Podsumowanie"
    _write_summary(summary, report)
    _write_products(workbook.create_sheet("Produkty"), report)
    _write_rows(workbook.create_sheet("Dane"), report)
    _write_problems(workbook.create_sheet("Problemy"), report)
    _write_checks(workbook.create_sheet("Kontrola"), report)
    workbook.save(path)
