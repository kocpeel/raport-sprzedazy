"""Command line: python -m raport --dane przyklad/dane --wyjscie wynik"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from .cleaning import KIND_DUPLICATE, KIND_ERROR, KIND_WARNING
from .config import ConfigError, load_config
from .excel_report import write_excel
from .formatting import format_day, format_pln
from .html_report import write_html
from .pipeline import build_report


def _parse_day(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"„{text}” nie jest datą w formacie RRRR-MM-DD.") from error


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m raport",
        description="Łączy eksporty sprzedaży z kilku źródeł i tworzy raport w Excelu i HTML.",
    )
    parser.add_argument("--konfiguracja", type=Path, default=Path("config.toml"), help="plik z opisem źródeł")
    parser.add_argument("--dane", type=Path, required=True, help="katalog z plikami wejściowymi")
    parser.add_argument("--wyjscie", type=Path, default=Path("wynik"), help="katalog na gotowy raport")
    parser.add_argument("--od", type=_parse_day, help="pierwszy dzień raportu, RRRR-MM-DD")
    parser.add_argument("--do", type=_parse_day, help="ostatni dzień raportu, RRRR-MM-DD")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    # Polish characters must print correctly in any Windows console.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    try:
        if args.od and args.do and args.od > args.do:
            raise ConfigError("Data --od jest późniejsza niż data --do.")
        config = load_config(args.konfiguracja)
        report = build_report(config, args.dane, args.od, args.do)
        args.wyjscie.mkdir(parents=True, exist_ok=True)
        excel_path = args.wyjscie / "raport.xlsx"
        html_path = args.wyjscie / "raport.html"
        write_excel(report, excel_path)
        write_html(report, html_path)
    except ConfigError as error:
        print(f"Błąd: {error}", file=sys.stderr)
        return 2
    except PermissionError as error:
        print(f"Błąd: nie mogę zapisać pliku {error.filename}. Zamknij go w Excelu i spróbuj ponownie.", file=sys.stderr)
        return 2

    print(f"Okres: {format_day(report.first_day)} – {format_day(report.last_day)}")
    print(f"Przychód po zwrotach: {format_pln(report.revenue_gr)}, zamówienia: {report.orders}")
    for stats in report.sources:
        print(
            f"  {stats.name}: wczytano {stats.read}, w raporcie {stats.in_report}, "
            f"anulowane {stats.cancelled}, duplikaty {stats.duplicates}, błędy {stats.errors}, "
            f"pominięte {stats.skipped}, poza okresem {stats.out_of_period}"
        )
        if stats.total_difference_gr:
            print(f"    Różnica względem sumy w pliku: {format_pln(stats.total_difference_gr)}")

    counts = {
        kind: sum(1 for problem in report.problems if problem.kind == kind)
        for kind in (KIND_ERROR, KIND_WARNING, KIND_DUPLICATE)
    }
    print(
        f"Do sprawdzenia: błędy {counts[KIND_ERROR]}, ostrzeżenia {counts[KIND_WARNING]}, "
        f"duplikaty {counts[KIND_DUPLICATE]}"
    )
    print(f"Zapisano: {excel_path}")
    print(f"Zapisano: {html_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
