"""Generates the fictional sample files, deliberately messy, the way real exports tend to be.

It also writes oczekiwane.json: the correct totals, calculated before any mess is added.
The tests compare the finished report against that file.

Run: python przyklad/generuj_dane.py
"""

from __future__ import annotations

import csv
import json
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from openpyxl import Workbook

OUTPUT = Path(__file__).parent / "dane"
EXPECTED = Path(__file__).parent / "oczekiwane.json"
SEED = 20260630
FIRST_DAY = date(2026, 1, 1)
LAST_DAY = date(2026, 6, 30)

# name, category, price in grosze, marketplace title, till abbreviation
PRODUCTS = [
    ("Kubek termiczny 450 ml", "Kuchnia", 5990, "KUBEK TERMICZNY 450ML stal nierdzewna", "Kubek term. 450"),
    ("Butelka filtrująca 700 ml", "Kuchnia", 7900, "Butelka z filtrem 700ml", "Butelka filtr 700"),
    ("Zestaw pojemników 5 szt.", "Kuchnia", 9900, "Pojemniki na żywność komplet 5 szt", "Pojemniki 5szt"),
    ("Lampka biurkowa LED", "Dom", 12900, "LAMPKA BIURKOWA LED ściemnialna", "Lampka LED"),
    ("Świeca sojowa", "Dom", 3900, "Świeca sojowa zapachowa", "Swieca soj."),
    ("Organizer na biurko", "Biuro", 4990, "Organizer na biurko drewniany", "Organizer biurk."),
    ("Notes w twardej oprawie", "Biuro", 2990, "Notes A5 twarda oprawa", "Notes tw."),
    ("Plecak miejski 20 l", "Akcesoria", 18900, "Plecak miejski 20L wodoodporny", "Plecak 20l"),
    ("Ręcznik szybkoschnący", "Akcesoria", 4500, "Ręcznik szybkoschnący mikrofibra", "Recznik szybk."),
    ("Mata do jogi", "Sport", 11900, "MATA DO JOGI antypoślizgowa", "Mata joga"),
]

# A stronger second quarter, so the monthly chart has a shape.
MONTH_WEIGHTS = {1: 0.8, 2: 0.75, 3: 0.95, 4: 1.05, 5: 1.2, 6: 1.3}


@dataclass
class Sale:
    number: str
    day: date
    product: tuple
    quantity: int
    price_gr: int
    status: str = "sprzedaz"


def random_day(rng: random.Random) -> date:
    while True:
        day = FIRST_DAY + timedelta(days=rng.randrange((LAST_DAY - FIRST_DAY).days + 1))
        if rng.random() < MONTH_WEIGHTS[day.month] / 1.3:
            return day


def make_sales(rng: random.Random, prefix: str, count: int, cancelled: float, returned: float) -> list[Sale]:
    sales = []
    for index in range(count):
        status = "sprzedaz"
        roll = rng.random()
        if roll < cancelled:
            status = "anulowane"
        elif roll < cancelled + returned:
            status = "zwrot"
        product = rng.choice(PRODUCTS)
        sales.append(
            Sale(
                number=f"{prefix}{10000 + index}",
                day=random_day(rng),
                product=product,
                quantity=rng.choices([1, 2, 3], weights=[80, 15, 5])[0],
                price_gr=product[2],
                status=status,
            )
        )
    return sorted(sales, key=lambda sale: (sale.day, sale.number))


def signed_value(sale: Sale) -> int:
    return sale.quantity * sale.price_gr * (-1 if sale.status == "zwrot" else 1)


def polish_amount(grosze: int, currency: bool, rng: random.Random) -> str:
    whole, fraction = divmod(grosze, 100)
    text = f"{whole},{fraction:02d}"
    if whole >= 1000:
        text = f"{whole // 1000} {whole % 1000:03d},{fraction:02d}"
    return f"{text} zł" if currency and rng.random() < 0.5 else text


def write_online(rng: random.Random) -> dict:
    sales = make_sales(rng, "WWW-", 520, cancelled=0.05, returned=0.03)
    expected = {"wartosc_gr": 0, "w_raporcie": 0, "anulowane": 0, "duplikaty": 0, "bledy": 0, "ostrzezenia": 0}
    statuses = {"sprzedaz": "zrealizowane", "anulowane": "anulowane", "zwrot": "zwrot"}
    rows = []

    for index, sale in enumerate(sales):
        name = sale.product[0]
        if rng.random() < 0.08:
            name = f"  {name.replace(' ', '  ', 1)} "
        stamp = datetime.combine(sale.day, datetime.min.time()) + timedelta(minutes=rng.randrange(8 * 60, 22 * 60))
        row = [
            sale.number,
            stamp.strftime("%Y-%m-%d %H:%M"),
            name,
            str(sale.quantity),
            polish_amount(sale.price_gr, True, rng),
            statuses[sale.status].upper() if rng.random() < 0.1 else statuses[sale.status],
        ]

        if sale.status == "anulowane":
            expected["anulowane"] += 1
            rows.append(row)
            continue

        # Every 90th row is broken on purpose.
        if index % 90 == 45:
            variant = (index // 90) % 3
            if variant == 0:
                row[1] = "brak daty"
            elif variant == 1:
                row[3] = "dużo"
            else:
                row[4] = ""
            expected["bledy"] += 1
            rows.append(row)
            continue

        expected["wartosc_gr"] += signed_value(sale)
        expected["w_raporcie"] += 1
        rows.append(row)

        # The same line exported twice.
        if index % 37 == 11:
            rows.append(list(row))
            expected["duplikaty"] += 1

    path = OUTPUT / "sklep_online.csv"
    with path.open("w", encoding="cp1250", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["Nr zamówienia", "Data zamówienia", "Produkt", "Ilość", "Cena brutto", "Status"])
        writer.writerows(rows)
    return expected


def write_marketplace(rng: random.Random) -> dict:
    sales = make_sales(rng, "MP", 610, cancelled=0.04, returned=0.05)
    expected = {"wartosc_gr": 0, "w_raporcie": 0, "anulowane": 0, "duplikaty": 0, "bledy": 0, "ostrzezenia": 0}
    statuses = {"sprzedaz": "PAID", "anulowane": "CANCELLED", "zwrot": "RETURNED"}
    rows = []

    for index, sale in enumerate(sales):
        title = sale.product[3]
        row = [
            sale.number,
            sale.day.strftime("%d.%m.%Y"),
            title,
            str(sale.quantity),
            f"{sale.price_gr / 100:.2f}",
            statuses[sale.status],
        ]

        if sale.status == "anulowane":
            expected["anulowane"] += 1
            rows.append(row)
            continue

        if index % 120 == 60:
            row[1] = "31.02.2026"
            expected["bledy"] += 1
            rows.append(row)
            continue

        # A product added to the shop but not yet to the product list. It still counts as revenue.
        if index % 150 == 75:
            row[2] = "Termos stalowy 1 l NOWOŚĆ"
            expected["ostrzezenia"] += 1

        expected["wartosc_gr"] += signed_value(sale)
        expected["w_raporcie"] += 1
        rows.append(row)

        if index % 41 == 13:
            rows.append(list(row))
            expected["duplikaty"] += 1

    path = OUTPUT / "marketplace.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=",")
        writer.writerow(["order_id", "created_at", "offer_title", "quantity", "unit_price", "state"])
        writer.writerows(rows)
    return expected


POLISH_MONTHS = ("sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru")


def write_till(rng: random.Random) -> dict:
    sales = make_sales(rng, "PAR/", 430, cancelled=0, returned=0)
    expected = {"wartosc_gr": 0, "w_raporcie": 0, "anulowane": 0, "duplikaty": 0, "bledy": 0, "ostrzezenia": 0}
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Kasa"
    sheet["A1"] = "Raport kasowy: sklep stacjonarny"
    sheet["A2"] = f"Okres: {FIRST_DAY:%d.%m.%Y} - {LAST_DAY:%d.%m.%Y}"
    sheet.append([])
    sheet.append(["Paragon", "Data", "Towar", "Szt.", "Cena", "Wartość"])

    declared = 0
    for index, sale in enumerate(sales):
        value = sale.quantity * sale.price_gr
        price: object = sale.price_gr / 100
        if index % 7 == 0:
            price = polish_amount(sale.price_gr, True, rng)

        day: object = datetime.combine(sale.day, datetime.min.time())
        if index % 9 == 0:
            day = f"{sale.day.day} {POLISH_MONTHS[sale.day.month - 1]} {sale.day.year}"

        # The till's own total counts every receipt, including ones with an unreadable date.
        declared += value
        if index % 100 == 50:
            day = "??.??.2026"
            expected["bledy"] += 1
        else:
            expected["wartosc_gr"] += value
            expected["w_raporcie"] += 1

        sheet.append([sale.number, day, sale.product[4], sale.quantity, price, value / 100])

    sheet.append([])
    sheet.append(["SUMA", None, None, None, None, declared / 100])
    expected["pominiete"] = 2
    expected["suma_z_pliku_gr"] = declared
    workbook.save(OUTPUT / "kasa_sklep.xlsx")
    return expected


def write_products() -> None:
    path = OUTPUT / "produkty.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["nazwa", "kategoria", "aliasy"])
        for name, category, _, marketplace, till in PRODUCTS:
            writer.writerow([name, category, f"{marketplace}|{till}"])


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    write_products()
    expected = {
        "Sklep internetowy": write_online(rng),
        "Marketplace": write_marketplace(rng),
        "Sklep stacjonarny": write_till(rng),
    }
    EXPECTED.write_text(json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Zapisano dane przykładowe w {OUTPUT}")


if __name__ == "__main__":
    main()
