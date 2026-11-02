"""Connects the steps: read, clean, summarise."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from .cleaning import Catalog, Problem, SourceStats, clean_source
from .config import Config, ConfigError
from .readers import read_source

ROW_COLUMNS = [
    "source", "number", "day", "product", "category", "quantity", "price_gr", "value_gr", "is_return",
]


@dataclass
class Report:
    company: str
    note: str | None
    rows: pd.DataFrame
    problems: list[Problem]
    sources: list[SourceStats]
    channels: list[str]
    months: list[str]
    month_values: dict[str, dict[str, int]]
    products: pd.DataFrame
    categories: pd.DataFrame
    revenue_gr: int
    sales_gr: int
    returns_gr: int
    orders: int
    units: int
    first_day: date
    last_day: date

    @property
    def average_order_gr(self) -> int:
        return round(self.sales_gr / self.orders) if self.orders else 0


def _month_range(rows: pd.DataFrame) -> list[str]:
    # Months with no sales still appear, so a gap in the data is visible on the chart.
    periods = pd.to_datetime(rows["day"]).dt.to_period("M")
    return [str(period) for period in pd.period_range(periods.min(), periods.max(), freq="M")]


def build_report(
    config: Config,
    data_dir: Path,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Report:
    catalog = Catalog.load(data_dir / config.products_file)
    results = [
        clean_source(source, read_source(source, data_dir), catalog, date_from, date_to)
        for source in config.sources
    ]

    for result in results:
        if not result.stats.balanced:
            raise AssertionError(f"Liczby wierszy się nie zgadzają dla źródła {result.stats.name}: {result.stats}")

    all_rows = [row for result in results for row in result.rows]
    if not all_rows:
        raise ConfigError("Żaden wiersz nie trafił do raportu. Sprawdź pliki wejściowe i wybrany okres.")

    rows = pd.DataFrame([asdict(row) for row in all_rows], columns=ROW_COLUMNS)
    rows = rows.sort_values(["day", "source", "number"], kind="stable").reset_index(drop=True)
    rows["month"] = pd.to_datetime(rows["day"]).dt.strftime("%Y-%m")

    channels = [source.name for source in config.sources]
    months = _month_range(rows)
    pivot = rows.pivot_table(index="month", columns="source", values="value_gr", aggfunc="sum", fill_value=0)
    pivot = pivot.reindex(index=months, columns=channels, fill_value=0)
    month_values = {
        month: {channel: int(pivot.loc[month, channel]) for channel in channels} for month in months
    }

    products = (
        rows.groupby(["product", "category"], as_index=False)
        .agg(value_gr=("value_gr", "sum"), units=("quantity", "sum"))
        .sort_values(["value_gr", "product"], ascending=[False, True])
        .reset_index(drop=True)
    )
    categories = (
        rows.groupby("category", as_index=False)
        .agg(value_gr=("value_gr", "sum"), units=("quantity", "sum"))
        .sort_values(["value_gr", "category"], ascending=[False, True])
        .reset_index(drop=True)
    )

    sales = rows[~rows["is_return"]]
    returns = rows[rows["is_return"]]
    order_keys = sales[["source", "number"]].drop_duplicates()

    return Report(
        company=config.company,
        note=config.note,
        rows=rows,
        problems=[problem for result in results for problem in result.problems],
        sources=[result.stats for result in results],
        channels=channels,
        months=months,
        month_values=month_values,
        products=products,
        categories=categories,
        revenue_gr=int(rows["value_gr"].sum()),
        sales_gr=int(sales["value_gr"].sum()),
        returns_gr=int(-returns["value_gr"].sum()),
        orders=len(order_keys),
        units=int(rows["quantity"].sum()),
        first_day=rows["day"].min(),
        last_day=rows["day"].max(),
    )
