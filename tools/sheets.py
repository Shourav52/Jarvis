"""create_spreadsheet: formatted Excel table with optional totals and chart."""
import re

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

from .common import after_create, output_path

TOOLS = [{
    "type": "function",
    "function": {
        "name": "create_spreadsheet",
        "description": "Create an Excel (.xlsx) spreadsheet from table data.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "headers": {"type": "array", "items": {"type": "string"}},
                "rows": {"type": "array", "items": {"type": "array", "items": {"type": ["string", "number"]}}},
                "add_totals": {"type": "boolean", "description": "Add a SUM row for numeric columns"},
                "chart": {"type": "string", "enum": ["none", "bar", "line"]},
            },
            "required": ["title", "headers", "rows"],
        },
    },
}]

NUM = re.compile(r"^-?[\d,]*\.?\d+$")


def _num(v):
    if isinstance(v, (int, float)):
        return v
    s = str(v).strip().replace("$", "").replace("৳", "").replace("%", "")
    if s and NUM.match(s):
        s = s.replace(",", "")
        return float(s) if "." in s else int(s)
    return v


def create_spreadsheet(args):
    title = args.get("title") or "Spreadsheet"
    headers = [str(h) for h in (args.get("headers") or [])]
    rows = args.get("rows") or []
    if not headers or not rows:
        return "I need column headers and at least one row."
    print(f"[Creating spreadsheet: {title}]")

    # unique, non-empty headers (Excel table needs them)
    seen, clean = set(), []
    for i, h in enumerate(headers):
        h = h.strip() or f"Column {i + 1}"
        while h in seen:
            h += "_"
        seen.add(h)
        clean.append(h)
    headers, ncol = clean, len(clean)
    data = [[_num(v) for v in (list(r) + [""] * ncol)[:ncol]] for r in rows]

    wb = Workbook()
    ws = wb.active
    ws.title = (re.sub(r"[\[\]\*\?:/\\]", " ", title).strip() or "Sheet1")[:31]
    base = Font(name="Arial", size=11)
    ws.append(headers)
    for r in data:
        ws.append(r)
    last = len(data) + 1

    numeric = []
    for c in range(ncol):
        vals = [r[c] for r in data]
        if sum(isinstance(v, (int, float)) for v in vals) >= 0.6 * len(vals):
            numeric.append(c)

    thin = Side(style="thin", color="D0D7E8")
    for row in ws.iter_rows(min_row=1, max_row=last, max_col=ncol):
        for cell in row:
            cell.font = base
            cell.border = Border(top=thin, bottom=thin, left=thin, right=thin)
            cell.alignment = Alignment(vertical="center", wrap_text=False)
    for c in range(ncol):
        head = ws.cell(row=1, column=c + 1)
        head.font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
        head.alignment = Alignment(horizontal="center", vertical="center")
        if c in numeric:
            vals = [r[c] for r in data if isinstance(r[c], (int, float))]
            fmt = "#,##0.00" if any(isinstance(v, float) and v != int(v) for v in vals) else "#,##0"
            for r in range(2, last + 1):
                ws.cell(row=r, column=c + 1).number_format = fmt
                ws.cell(row=r, column=c + 1).alignment = Alignment(horizontal="right")
        width = max(len(str(v)) for v in [headers[c]] + [r[c] for r in data])
        ws.column_dimensions[get_column_letter(c + 1)].width = min(max(width + 4, 12), 50)
    ws.row_dimensions[1].height = 24

    tab = Table(displayName="Data", ref=f"A1:{get_column_letter(ncol)}{last}")
    tab.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
    ws.add_table(tab)
    ws.freeze_panes = "A2"

    if args.get("add_totals") and numeric:
        tr = last + 1
        ws.cell(row=tr, column=1, value="Total").font = Font(name="Arial", size=11, bold=True)
        for c in numeric:
            if c == 0:
                continue
            L = get_column_letter(c + 1)
            cell = ws.cell(row=tr, column=c + 1, value=f"=SUM({L}2:{L}{last})")
            cell.font = Font(name="Arial", size=11, bold=True)
            cell.number_format = ws.cell(row=2, column=c + 1).number_format
            cell.alignment = Alignment(horizontal="right")
        for c in range(ncol):
            ws.cell(row=tr, column=c + 1).fill = PatternFill("solid", fgColor="E8EEFC")

    kind = args.get("chart") or "none"
    value_cols = [c for c in numeric if c != 0]
    if kind in ("bar", "line") and value_cols and len(data) >= 2:
        ch = BarChart() if kind == "bar" else LineChart()
        ch.title = title
        ch.height, ch.width = 9, 17
        for c in value_cols[:4]:
            ch.add_data(Reference(ws, min_col=c + 1, min_row=1, max_row=last), titles_from_data=True)
        ch.set_categories(Reference(ws, min_col=1, min_row=2, max_row=last))
        ws.add_chart(ch, f"{get_column_letter(ncol + 2)}2")

    path = output_path(title, "xlsx")
    wb.save(path)
    opened = after_create(path)
    return f"Saved {path.rsplit('/', 1)[-1]} in the 'documents' folder ({len(data)} rows).{opened}"


HANDLERS = {"create_spreadsheet": create_spreadsheet}