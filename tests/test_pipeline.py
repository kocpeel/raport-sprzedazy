import json
import shutil
from datetime import date
from pathlib import Path

import pytest
from openpyxl import load_workbook

from raport.__main__ import main
from raport.config import ConfigError, load_config
from raport.excel_report import write_excel
from raport.html_report import render_html
from raport.pipeline import build_report

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "przyklad" / "dane"
EXPECTED = json.loads((ROOT / "przyklad" / "oczekiwane.json").read_text(encoding="utf-8"))
CONFIG = ROOT / "config.toml"


@pytest.fixture(scope="module")
def report():
    return build_report(load_config(CONFIG), SAMPLE)


def write_config(tmp_path, body):
    path = tmp_path / "config.toml"
    path.write_text(body, encoding="utf-8")
    return path


MINIMAL_CONFIG = """
[raport]
firma = "Test"
produkty = "produkty.csv"

[[zrodla]]
nazwa = "Sklep"
plik = "sklep.csv"
separator = ";"
kodowanie = "utf-8"

[zrodla.kolumny]
numer = "Nr"
data = "Data"
produkt = "Produkt"
ilosc = "Ilość"
cena = "Cena"
"""


def prepare_minimal(tmp_path, csv_text):
    (tmp_path / "produkty.csv").write_text("nazwa;kategoria;aliasy\nKubek;Kuchnia;\n", encoding="utf-8")
    (tmp_path / "sklep.csv").write_text(csv_text, encoding="utf-8")
    return load_config(write_config(tmp_path, MINIMAL_CONFIG))


def test_report_matches_totals_known_before_the_data_was_messed_up(report):
    assert report.revenue_gr == sum(item["wartosc_gr"] for item in EXPECTED.values())
    for stats in report.sources:
        expected = EXPECTED[stats.name]
        assert stats.value_gr == expected["wartosc_gr"], stats.name
        assert stats.in_report == expected["w_raporcie"], stats.name
        assert stats.cancelled == expected["anulowane"], stats.name
        assert stats.duplicates == expected["duplikaty"], stats.name
        assert stats.errors == expected["bledy"], stats.name
        assert stats.warnings == expected["ostrzezenia"], stats.name


def test_every_row_is_accounted_for(report):
    for stats in report.sources:
        assert stats.balanced, stats


def test_till_total_difference_equals_rejected_receipts(report):
    till = next(stats for stats in report.sources if stats.name == "Sklep stacjonarny")
    assert till.declared_total_gr == EXPECTED["Sklep stacjonarny"]["suma_z_pliku_gr"]
    assert till.skipped == EXPECTED["Sklep stacjonarny"]["pominiete"]
    assert till.total_difference_gr > 0
    assert till.errors > 0


def test_summary_tables_add_up_to_the_same_total(report):
    from_months = sum(sum(values.values()) for values in report.month_values.values())
    assert from_months == report.revenue_gr
    assert int(report.products["value_gr"].sum()) == report.revenue_gr
    assert int(report.categories["value_gr"].sum()) == report.revenue_gr
    assert report.sales_gr - report.returns_gr == report.revenue_gr


def test_all_aliases_are_matched_to_one_product_per_item(report):
    named = set(report.products["product"])
    assert "Kubek termiczny 450 ml" in named
    assert not any(name.isupper() for name in named)
    assert len(named) == 11  # ten products from the list and one unknown product


def test_months_without_sales_still_appear(tmp_path):
    config = prepare_minimal(
        tmp_path,
        "Nr;Data;Produkt;Ilość;Cena\nA;2026-01-10;Kubek;1;10,00\nB;2026-03-10;Kubek;1;10,00\n",
    )
    result = build_report(config, tmp_path)
    assert result.months == ["2026-01", "2026-02", "2026-03"]
    assert result.month_values["2026-02"]["Sklep"] == 0


def test_period_limits_report(tmp_path):
    config = prepare_minimal(
        tmp_path,
        "Nr;Data;Produkt;Ilość;Cena\nA;2026-01-10;Kubek;1;10,00\nB;2026-03-10;Kubek;2;10,00\n",
    )
    result = build_report(config, tmp_path, date(2026, 3, 1), date(2026, 3, 31))
    assert result.revenue_gr == 2000
    assert result.sources[0].out_of_period == 1


def test_missing_column_gives_a_message_naming_the_file(tmp_path):
    config = prepare_minimal(tmp_path, "Nr;Data;Nazwa;Ilość;Cena\nA;2026-01-10;Kubek;1;10,00\n")
    with pytest.raises(ConfigError, match=r"sklep\.csv brakuje kolumn: Produkt"):
        build_report(config, tmp_path)


def test_missing_file_gives_a_clear_message(tmp_path):
    config = prepare_minimal(tmp_path, "Nr;Data;Produkt;Ilość;Cena\n")
    (tmp_path / "sklep.csv").unlink()
    with pytest.raises(ConfigError, match="Nie znaleziono pliku"):
        build_report(config, tmp_path)


def test_wrong_encoding_gives_a_clear_message(tmp_path):
    config = prepare_minimal(tmp_path, "")
    (tmp_path / "sklep.csv").write_bytes("Nr;Data;Produkt;Ilość;Cena\n".encode("cp1250"))
    with pytest.raises(ConfigError, match="kodowaniem"):
        build_report(config, tmp_path)


def test_no_usable_rows_gives_a_clear_message(tmp_path):
    config = prepare_minimal(tmp_path, "Nr;Data;Produkt;Ilość;Cena\nA;zła data;Kubek;1;10,00\n")
    with pytest.raises(ConfigError, match="Żaden wiersz"):
        build_report(config, tmp_path)


def test_config_rejects_an_unknown_status_meaning(tmp_path):
    body = MINIMAL_CONFIG + 'status = "S"\n\n[zrodla.statusy]\nok = "cos-innego"\n'
    with pytest.raises(ConfigError, match="status może oznaczać"):
        load_config(write_config(tmp_path, body))


def test_excel_contains_the_same_numbers_and_charts(report, tmp_path):
    path = tmp_path / "raport.xlsx"
    write_excel(report, path)
    workbook = load_workbook(path)
    assert workbook.sheetnames == ["Podsumowanie", "Produkty", "Dane", "Problemy", "Kontrola"]

    summary = workbook["Podsumowanie"]
    assert summary["B4"].value == pytest.approx(report.revenue_gr / 100)
    assert len(summary._charts) == 1
    assert len(workbook["Produkty"]._charts) == 1

    data = workbook["Dane"]
    assert data.max_row - 1 == len(report.rows)
    total = sum(row[7] for row in data.iter_rows(min_row=2, values_only=True))
    assert total == pytest.approx(report.revenue_gr / 100)
    assert data.auto_filter.ref.startswith("A1:I")

    assert workbook["Problemy"].max_row - 1 == len(report.problems)


def test_html_escapes_names_from_the_data(tmp_path):
    config = prepare_minimal(
        tmp_path,
        "Nr;Data;Produkt;Ilość;Cena\nA;2026-01-10;<script>alert(1)</script>;1;10,00\nB;zła;Kubek;1;10,00\n",
    )
    html = render_html(build_report(config, tmp_path))
    assert "<script>alert(1)" not in html
    assert "&lt;script&gt;alert(1)" in html


def test_command_line_writes_both_reports(tmp_path, capsys):
    data = tmp_path / "dane"
    shutil.copytree(SAMPLE, data)
    output = tmp_path / "wynik"
    code = main(["--konfiguracja", str(CONFIG), "--dane", str(data), "--wyjscie", str(output)])
    assert code == 0
    assert (output / "raport.xlsx").exists()
    assert (output / "raport.html").exists()
    assert "Przychód po zwrotach" in capsys.readouterr().out


def test_command_line_reports_problems_without_a_traceback(tmp_path, capsys):
    code = main(["--konfiguracja", str(CONFIG), "--dane", str(tmp_path), "--wyjscie", str(tmp_path / "wynik")])
    assert code == 2
    captured = capsys.readouterr()
    assert "Błąd:" in captured.err
    assert "Traceback" not in captured.err
