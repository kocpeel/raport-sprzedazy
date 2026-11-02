"""Writes a single self-contained HTML report that can be opened or e-mailed without a server."""

from __future__ import annotations

import json
from html import escape
from pathlib import Path

from .cleaning import KIND_DUPLICATE, KIND_ERROR, KIND_WARNING
from .formatting import format_day, format_month, format_pln, group_digits, plural
from .pipeline import Report

MAX_PROBLEMS_SHOWN = 12
TOP_PRODUCTS = 10

STYLE = """
/* Layout: one reading column with the report's figures first and the data checks last. */
:root {
  --bg: #f9f9f7;
  --surface: #fcfcfb;
  --ink: #0b0b0b;
  --ink-2: #52514e;
  --ink-3: #6f6e69;
  --grid: #e1e0d9;
  --axis: #c3c2b7;
  --border: rgba(11, 11, 11, 0.1);
  --series-1: #2a78d6;
  --series-2: #eb6834;
  --series-3: #1baf7a;
  --critical: #b52f2f;
  --warning-bg: #fdf3d8;
  --warning-line: #c98500;
  --font-display: 'Manrope', 'Segoe UI', system-ui, sans-serif;
  --font-body: 'Source Sans 3', 'Segoe UI', system-ui, sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme='light']) {
    --bg: #0d0d0d;
    --surface: #1a1a19;
    --ink: #f0efec;
    --ink-2: #c3c2b7;
    --ink-3: #a3a29a;
    --grid: #2c2c2a;
    --axis: #4a4a46;
    --border: rgba(255, 255, 255, 0.1);
    --series-1: #3987e5;
    --series-2: #d95926;
    --series-3: #199e70;
    --critical: #f08a8a;
    --warning-bg: #33280c;
    --warning-line: #c98500;
    color-scheme: dark;
  }
}
:root[data-theme='dark'] {
  --bg: #0d0d0d;
  --surface: #1a1a19;
  --ink: #f0efec;
  --ink-2: #c3c2b7;
  --ink-3: #a3a29a;
  --grid: #2c2c2a;
  --axis: #4a4a46;
  --border: rgba(255, 255, 255, 0.1);
  --series-1: #3987e5;
  --series-2: #d95926;
  --series-3: #199e70;
  --critical: #f08a8a;
  --warning-bg: #33280c;
  --warning-line: #c98500;
  color-scheme: dark;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font: 400 1rem/1.5 var(--font-body);
}
.page {
  display: flex;
  flex-direction: column;
  gap: 28px;
  max-width: 1040px;
  margin: 0 auto;
  padding-block: 32px 56px;
  padding-left: max(16px, env(safe-area-inset-left, 0px));
  padding-right: max(16px, env(safe-area-inset-right, 0px));
}
h1, h2 { margin: 0; font-family: var(--font-display); text-wrap: balance; }
h1 { font-size: 1.75rem; font-weight: 700; line-height: 1.2; }
h2 { font-size: 1.125rem; font-weight: 700; }
p { margin: 0; }
.lead { margin-top: 4px; color: var(--ink-2); }
.note {
  padding: 6px 10px;
  border-left: 3px solid var(--warning-line);
  background: var(--warning-bg);
  font-size: 0.875rem;
}
.figures {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--border);
  overflow: hidden;
}
.figure { display: flex; flex-direction: column; gap: 2px; min-width: 0; padding: 14px 16px; background: var(--surface); }
.figure span { color: var(--ink-2); font-size: 0.875rem; }
.figure strong { font: 700 1.5rem/1.25 var(--font-display); overflow-wrap: break-word; }
.figure small { color: var(--ink-3); font-size: 0.8125rem; }
section { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.section-note { margin-top: -8px; color: var(--ink-2); font-size: 0.9375rem; }
.card {
  min-width: 0;
  padding: 16px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--surface);
}
.legend { display: flex; flex-wrap: wrap; gap: 4px 16px; margin: 0 0 8px; padding: 0; list-style: none; font-size: 0.875rem; color: var(--ink-2); }
.legend li { display: inline-flex; align-items: center; gap: 6px; }
.legend i { width: 12px; height: 12px; border-radius: 2px; }
.chart { position: relative; height: 280px; }
.chart svg { display: block; overflow: visible; }
.grid-line { stroke: var(--grid); }
.base-line { stroke: var(--axis); }
.tick { fill: var(--ink-3); font: 400 12px var(--font-body); font-variant-numeric: tabular-nums; }
.value { fill: var(--ink); font: 600 13px var(--font-body); }
.hit { fill: transparent; }
.hit:focus-visible { outline: none; stroke: var(--ink-2); stroke-width: 2; }
.column.active path { opacity: 0.82; }
.tooltip {
  position: absolute;
  z-index: 2;
  width: 214px;
  padding: 8px 10px;
  border: 1px solid var(--axis);
  border-radius: 4px;
  background: var(--surface);
  color: var(--ink-2);
  font-size: 0.8125rem;
  pointer-events: none;
}
.tooltip b { display: block; color: var(--ink); font-size: 0.9375rem; }
.tooltip div { display: flex; align-items: center; gap: 6px; }
.tooltip i { flex: none; width: 12px; height: 2px; }
.tooltip em { margin-left: auto; color: var(--ink); font-style: normal; font-weight: 600; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 0.9375rem; }
th { padding: 6px 10px; border-bottom: 1px solid var(--axis); color: var(--ink-2); font-size: 0.8125rem; font-weight: 600; text-align: left; white-space: nowrap; }
td { padding: 7px 10px; border-bottom: 1px solid var(--grid); vertical-align: top; }
tr:last-child td { border-bottom: 0; }
tfoot td { border-top: 1px solid var(--axis); font-weight: 600; }
.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.bars { display: flex; flex-direction: column; margin: 0; padding: 0; list-style: none; }
.bar-row { display: grid; grid-template-columns: minmax(0, 15rem) minmax(0, 1fr); align-items: center; gap: 12px; padding: 5px 0; font-size: 0.9375rem; }
.bar-track { display: flex; align-items: center; gap: 8px; min-width: 0; }
.bar { flex: none; width: calc((100% - 7.5rem) * var(--share)); min-width: 2px; height: 14px; border-radius: 0 4px 4px 0; background: var(--series-1); }
.bar-value { font-variant-numeric: tabular-nums; white-space: nowrap; }
.raw { color: var(--ink-2); font-size: 0.8125rem; overflow-wrap: break-word; }
.file { display: block; color: var(--ink-3); font-size: 0.8125rem; }
.table-wrap table { min-width: 620px; }
.table-wrap td:first-child { white-space: nowrap; }
.kind { font-weight: 600; white-space: nowrap; }
.kind-error { color: var(--critical); }
.check-ok { color: var(--ink-2); font-size: 0.9375rem; }
footer { color: var(--ink-3); font-size: 0.8125rem; }
@media (max-width: 720px) {
  h1 { font-size: 1.5rem; }
  .figures { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .figure { padding: 12px; }
  .figure strong { font-size: 1.125rem; }
  .bar-row { grid-template-columns: minmax(0, 1fr); gap: 2px; }
  .bar { width: calc((100% - 7rem) * var(--share)); }
}
"""

SCRIPT = """
(function () {
  var data = JSON.parse(document.getElementById('chart-data').textContent);
  var host = document.getElementById('month-chart');
  var tip = document.getElementById('month-tip');
  var NS = 'http://www.w3.org/2000/svg';
  var money = new Intl.NumberFormat('pl-PL', { style: 'currency', currency: 'PLN' });
  var HEIGHT = 280, TOP = 26, BOTTOM = 26, LEFT = 66, RIGHT = 8, GAP = 2, MAX_BAR = 24, CORNER = 4;
  var svg = null;

  function node(name, attrs, text) {
    var item = document.createElementNS(NS, name);
    Object.keys(attrs).forEach(function (key) { item.setAttribute(key, attrs[key]); });
    if (text !== undefined) item.textContent = text;
    return item;
  }
  function compact(grosze) {
    var zloty = grosze / 100;
    if (zloty === 0) return '0';
    if (zloty < 1000) return Math.round(zloty) + ' zł';
    var thousands = zloty / 1000;
    return thousands.toLocaleString('pl-PL', { maximumFractionDigits: thousands < 10 ? 1 : 0 }) + ' tys. zł';
  }
  function axis(max) {
    var rough = Math.max(max, 1) / 4;
    var power = Math.pow(10, Math.floor(Math.log(rough) / Math.LN10));
    var step = [1, 2, 5, 10].map(function (f) { return f * power; }).filter(function (v) { return v >= rough; })[0];
    var ticks = [];
    for (var value = 0; value < max + step; value += step) ticks.push(value);
    return ticks;
  }
  function segment(x, y, width, height, rounded) {
    if (!rounded) return 'M' + x + ',' + (y + height) + 'V' + y + 'H' + (x + width) + 'V' + (y + height) + 'Z';
    var r = Math.min(CORNER, height, width / 2);
    return 'M' + x + ',' + (y + height) + 'V' + (y + r) + 'Q' + x + ',' + y + ' ' + (x + r) + ',' + y +
      'H' + (x + width - r) + 'Q' + (x + width) + ',' + y + ' ' + (x + width) + ',' + (y + r) +
      'V' + (y + height) + 'Z';
  }
  function showTip(month, center, top, width, barWidth) {
    tip.textContent = '';
    var total = document.createElement('b');
    total.textContent = money.format(month.total / 100);
    tip.appendChild(total);
    var label = document.createElement('span');
    label.textContent = month.label;
    tip.appendChild(label);
    data.channels.forEach(function (channel, index) {
      var row = document.createElement('div');
      var key = document.createElement('i');
      key.style.background = 'var(--series-' + (index + 1) + ')';
      var name = document.createElement('span');
      name.textContent = channel;
      var value = document.createElement('em');
      value.textContent = money.format(month.values[index] / 100);
      row.appendChild(key); row.appendChild(name); row.appendChild(value);
      tip.appendChild(row);
    });
    tip.hidden = false;
    // Beside the column rather than above it, so the tooltip never covers the bar it describes.
    var right = center + barWidth / 2 + 10;
    var left = right + 214 <= width ? right : center - barWidth / 2 - 224;
    tip.style.left = Math.max(0, left) + 'px';
    tip.style.top = Math.min(Math.max(0, top - 10), HEIGHT - 128) + 'px';
  }
  function draw() {
    var width = host.clientWidth;
    if (!width) return;
    if (svg) svg.remove();
    svg = node('svg', { width: width, height: HEIGHT, role: 'group', 'aria-label': 'Przychód według miesięcy i kanałów' });
    var max = Math.max.apply(null, data.months.map(function (m) { return m.total; }));
    var ticks = axis(max);
    var top = ticks[ticks.length - 1];
    var base = HEIGHT - BOTTOM;
    var plot = base - TOP;
    function y(value) { return base - (value / top) * plot; }
    ticks.forEach(function (tick) {
      svg.appendChild(node('line', { 'class': tick === 0 ? 'base-line' : 'grid-line', x1: LEFT, x2: width - RIGHT, y1: y(tick), y2: y(tick) }));
      svg.appendChild(node('text', { 'class': 'tick', x: LEFT - 8, y: y(tick), dy: '0.32em', 'text-anchor': 'end' }, compact(tick)));
    });
    var band = (width - LEFT - RIGHT) / data.months.length;
    var bar = Math.min(MAX_BAR, band * 0.6);
    var peak = data.months.reduce(function (best, m, i) { return m.total > data.months[best].total ? i : best; }, 0);
    var last = data.months.length - 1;
    data.months.forEach(function (month, index) {
      var center = LEFT + band * index + band / 2;
      var group = node('g', { 'class': 'column' });
      var stacked = 0;
      var topIndex = -1;
      month.values.forEach(function (v, i) { if (v > 0) topIndex = i; });
      month.values.forEach(function (value, i) {
        if (value <= 0) return;
        var upper = y(stacked + value);
        var lower = y(stacked);
        var height = Math.max(1, lower - upper - (stacked > 0 ? GAP : 0));
        group.appendChild(node('path', {
          d: segment(center - bar / 2, upper, bar, height, i === topIndex),
          fill: 'var(--series-' + (i + 1) + ')'
        }));
        stacked += value;
      });
      if (index === peak || index === last) {
        group.appendChild(node('text', { 'class': 'value', x: center, y: y(month.total) - 8, 'text-anchor': 'middle' }, compact(month.total)));
      }
      group.appendChild(node('text', { 'class': 'tick', x: center, y: HEIGHT - 8, 'text-anchor': 'middle' }, month.short));
      var hit = node('rect', {
        'class': 'hit', x: center - band / 2, y: 0, width: band, height: HEIGHT, tabindex: 0, role: 'img',
        'aria-label': month.label + ': ' + money.format(month.total / 100)
      });
      function enter() { group.classList.add('active'); showTip(month, center, y(month.total), width, bar); }
      function leave() { group.classList.remove('active'); tip.hidden = true; }
      hit.addEventListener('pointerenter', enter);
      hit.addEventListener('pointerleave', leave);
      hit.addEventListener('focus', enter);
      hit.addEventListener('blur', leave);
      group.appendChild(hit);
      svg.appendChild(group);
    });
    host.insertBefore(svg, tip);
  }
  draw();
  if (window.ResizeObserver) new ResizeObserver(draw).observe(host);
})();
"""

MONTH_SHORT = ("sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru")


def _chart_json(report: Report) -> str:
    data = {
        "channels": report.channels,
        "months": [
            {
                "label": format_month(month),
                "short": MONTH_SHORT[int(month[5:]) - 1],
                "values": [report.month_values[month][channel] for channel in report.channels],
                "total": sum(report.month_values[month].values()),
            }
            for month in report.months
        ],
    }
    # Escaping "<" keeps product or channel names from closing the script tag.
    return json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")


def _figures(report: Report) -> str:
    return_note = f"sprzedaż {format_pln(report.sales_gr)}, zwroty {format_pln(report.returns_gr)}"
    channels = len(report.channels)
    channel_note = f"{channels} {plural(channels, 'kanał', 'kanały', 'kanałów')} sprzedaży"
    items = [
        ("Przychód po zwrotach", format_pln(report.revenue_gr), return_note),
        ("Zamówienia", group_digits(report.orders), channel_note),
        ("Średnia wartość zamówienia", format_pln(report.average_order_gr), "bez zwrotów"),
        ("Sprzedane sztuki", group_digits(report.units), "po zwrotach"),
    ]
    cells = "".join(
        f'<div class="figure"><span>{escape(label)}</span><strong>{escape(value)}</strong>'
        f"<small>{escape(detail)}</small></div>"
        for label, value, detail in items
    )
    return f'<div class="figures">{cells}</div>'


def _month_section(report: Report) -> str:
    legend = "".join(
        f'<li><i style="background:var(--series-{index})"></i>{escape(channel)}</li>'
        for index, channel in enumerate(report.channels, start=1)
    )
    headers = "".join(f'<th class="num" scope="col">{escape(channel)}</th>' for channel in report.channels)
    rows = ""
    for month in report.months:
        values = report.month_values[month]
        cells = "".join(f'<td class="num">{format_pln(values[channel])}</td>' for channel in report.channels)
        rows += f'<tr><td>{format_month(month)}</td>{cells}<td class="num">{format_pln(sum(values.values()))}</td></tr>'
    totals = "".join(
        f'<td class="num">{format_pln(sum(report.month_values[month][channel] for month in report.months))}</td>'
        for channel in report.channels
    )
    return f"""
<section>
  <h2>Przychód według miesięcy</h2>
  <div class="card">
    <ul class="legend">{legend}</ul>
    <div class="chart" id="month-chart"><div class="tooltip" id="month-tip" hidden></div></div>
  </div>
  <div class="card table-wrap">
    <table>
      <thead><tr><th scope="col">Miesiąc</th>{headers}<th class="num" scope="col">Razem</th></tr></thead>
      <tbody>{rows}</tbody>
      <tfoot><tr><td>Razem</td>{totals}<td class="num">{format_pln(report.revenue_gr)}</td></tr></tfoot>
    </table>
  </div>
</section>"""


def _products_section(report: Report) -> str:
    top = report.products.head(TOP_PRODUCTS)
    highest = max(int(top["value_gr"].max()), 1)
    rows = "".join(
        f'<li class="bar-row"><span>{escape(row.product)}</span><span class="bar-track">'
        f'<span class="bar" style="--share:{max(int(row.value_gr), 0) / highest:.4f}"></span>'
        f'<span class="bar-value">{format_pln(int(row.value_gr))}</span></span></li>'
        for row in top.itertuples(index=False)
    )
    return f"""
<section>
  <h2>{len(top)} najlepszych produktów</h2>
  <div class="card"><ul class="bars">{rows}</ul></div>
</section>"""


def _checks_section(report: Report) -> str:
    rows = ""
    for stats in report.sources:
        if stats.total_difference_gr is None:
            difference = "brak sumy w pliku"
        else:
            difference = format_pln(stats.total_difference_gr)
        rows += (
            f"<tr><td>{escape(stats.name)}<small class=\"file\">{escape(stats.file)}</small></td>"
            f"<td class=\"num\">{stats.read}</td>"
            f"<td class=\"num\">{stats.in_report}</td><td class=\"num\">{stats.cancelled}</td>"
            f"<td class=\"num\">{stats.duplicates}</td><td class=\"num\">{stats.errors}</td>"
            f"<td class=\"num\">{stats.skipped}</td><td class=\"num\">{format_pln(stats.value_gr)}</td>"
            f"<td class=\"num\">{difference}</td></tr>"
        )

    errors = [problem for problem in report.problems if problem.kind == KIND_ERROR]
    warnings = sum(1 for problem in report.problems if problem.kind == KIND_WARNING)
    duplicates = sum(1 for problem in report.problems if problem.kind == KIND_DUPLICATE)
    summary = (
        f"Do sprawdzenia: {len(errors)} {plural(len(errors), 'błąd', 'błędy', 'błędów')}, "
        f"{warnings} {plural(warnings, 'ostrzeżenie', 'ostrzeżenia', 'ostrzeżeń')}, "
        f"{duplicates} {plural(duplicates, 'duplikat', 'duplikaty', 'duplikatów')}. "
        "Pełna lista jest w arkuszu Problemy w pliku Excel."
    )
    problem_rows = "".join(
        f'<tr><td class="kind{" kind-error" if problem.kind == KIND_ERROR else ""}">{escape(problem.kind)}</td>'
        f"<td>{escape(problem.source)}</td><td class=\"num\">{problem.line}</td>"
        f"<td>{escape(problem.reason)}</td><td class=\"raw\">{escape(problem.raw)}</td></tr>"
        for problem in errors[:MAX_PROBLEMS_SHOWN]
    )
    problems_table = (
        f"""<div class="card table-wrap"><table>
      <thead><tr><th scope="col">Rodzaj</th><th scope="col">Kanał</th><th class="num" scope="col">Wiersz</th>
      <th scope="col">Powód</th><th scope="col">Zawartość wiersza</th></tr></thead>
      <tbody>{problem_rows}</tbody></table></div>"""
        if problem_rows
        else ""
    )
    return f"""
<section>
  <h2>Kontrola danych</h2>
  <p class="section-note">Każdy wiersz z plików ma swoje miejsce. Różnica to suma podana w pliku minus wartość, która trafiła do raportu.</p>
  <div class="card table-wrap"><table>
    <thead><tr><th scope="col">Kanał</th><th class="num" scope="col">Wczytane</th><th class="num" scope="col">W raporcie</th>
    <th class="num" scope="col">Anulowane</th><th class="num" scope="col">Duplikaty</th><th class="num" scope="col">Błędy</th>
    <th class="num" scope="col">Pominięte</th><th class="num" scope="col">Wartość</th><th class="num" scope="col">Różnica</th></tr></thead>
    <tbody>{rows}</tbody>
  </table></div>
  <p class="check-ok">{escape(summary)}</p>
  {problems_table}
</section>"""


def render_body(report: Report) -> str:
    note = f'<p class="note">{escape(report.note)}</p>' if report.note else ""
    return f"""
<div class="page">
  <header>
    <h1>Raport sprzedaży: {escape(report.company)}</h1>
    <p class="lead">{format_day(report.first_day)} – {format_day(report.last_day)}</p>
  </header>
  {note}
  {_figures(report)}
  {_month_section(report)}
  {_products_section(report)}
  {_checks_section(report)}
  <footer>Raport wygenerowany automatycznie z plików źródłowych.</footer>
</div>
<script type="application/json" id="chart-data">{_chart_json(report)}</script>
<script>{SCRIPT}</script>"""


FONTS = (
    "https://fonts.googleapis.com/css2?family=Manrope:wght@600;700"
    "&family=Source+Sans+3:wght@400;600&display=swap"
)


def render_html(report: Report) -> str:
    return f"""<!doctype html>
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Raport sprzedaży: {escape(report.company)}</title>
<link rel="stylesheet" href="{FONTS}">
<style>{STYLE}</style>
</head>
<body>
{render_body(report)}
</body>
</html>
"""


def write_html(report: Report, path: Path) -> None:
    path.write_text(render_html(report), encoding="utf-8")
