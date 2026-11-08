"""Read a commercial invoice (plain text) into fields.

Plain Python, no AI. Every field keeps the line it came from ("evidence"),
so an officer can see where each value was read. A field that is not found
is None, which the comparison step later reports as MISSING.

Limit: this reads invoices that use "Label: value" lines and one goods row.
Other layouts need the AI fallback (a later step).
"""
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

FIELD_NAMES = [
    "invoice_number", "invoice_date", "seller", "buyer",
    "lc_number", "lc_date", "issuing_bank",
    "port_of_loading", "port_of_discharge", "shipment_date", "terms",
    "proforma_invoice",
    "goods_description", "quantity", "unit", "unit_price", "line_amount",
    "currency", "total_amount",
]

# Day first. 03/04/2026 is read as 3 April 2026.
DATE_FORMATS = ["%d %B %Y", "%d %b %Y", "%d-%b-%Y", "%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d"]

LABEL_LINE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 /().#&-]{1,40}?)\s*:\s*(.*)$")

SIMPLE_LABELS = {
    "invoice no": "invoice_number", "invoice number": "invoice_number",
    "invoice date": "invoice_date",
    "letter of credit no": "lc_number", "lc no": "lc_number",
    "lc number": "lc_number", "documentary credit no": "lc_number",
    "documentary credit number": "lc_number",
    "letter of credit date": "lc_date", "lc date": "lc_date",
    "issuing bank": "issuing_bank",
    "port of loading": "port_of_loading", "port of discharge": "port_of_discharge",
    "date of shipment": "shipment_date", "shipment date": "shipment_date",
    "shipped on board date": "shipment_date",
    "terms of delivery": "terms", "incoterms": "terms", "terms": "terms",
    "proforma invoice": "proforma_invoice",
    "total amount": "total",
}
BLOCK_LABELS = {
    "seller exporter": "seller", "seller": "seller", "exporter": "seller",
    "buyer applicant": "buyer", "buyer": "buyer", "applicant": "buyer",
}

GOODS_ROW = re.compile(
    r"^(?P<desc>.+?)\s+(?P<qty>\d[\d,]*(?:\.\d+)?)\s+(?P<unit>[A-Za-z]+)\s+"
    r"(?P<pcur>[A-Z]{3})\s*(?P<price>\d[\d,]*\.\d+)\s+"
    r"(?P<acur>[A-Z]{3})\s*(?P<amount>\d[\d,]*\.\d+)\s*$"
)
MONEY = re.compile(r"^([A-Z]{3})\s*(\d[\d,]*(?:\.\d+)?)$")


def _norm_label(label):
    return " ".join(re.sub(r"[^a-z0-9 ]", "", label.lower()).split())


def _one_line(text):
    return " ".join(text.split())


def _number(text):
    try:
        return Decimal(text.replace(",", ""))
    except InvalidOperation:
        return None


def parse_date(text):
    text = _one_line(text).strip(" .")
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_invoice(text):
    lines = text.replace("\r", "").split("\n")
    found = {name: None for name in FIELD_NAMES}
    warnings = []

    def put(name, value, evidence):
        if value is None or value == "":
            return
        if found[name] is None:  # the first one wins
            found[name] = {"value": value, "evidence": evidence}

    total_text = None
    for i, line in enumerate(lines):
        # goods row
        row = GOODS_ROW.match(line.strip())
        if row:
            ev = line.strip()
            put("goods_description", _one_line(row["desc"]), ev)
            put("quantity", _number(row["qty"]), ev)
            put("unit", row["unit"].upper(), ev)
            put("unit_price", _number(row["price"]), ev)
            put("line_amount", _number(row["amount"]), ev)
            found["_row_currencies"] = (row["pcur"], row["acur"])
            continue

        m = LABEL_LINE.match(line)
        if not m:
            continue
        label, value = _norm_label(m.group(1)), m.group(2).strip()

        if label in BLOCK_LABELS:
            block = [value] if value else []
            for nxt in lines[i + 1:]:
                if not nxt.strip() or LABEL_LINE.match(nxt):
                    break
                block.append(nxt.strip())
            if block:
                put(BLOCK_LABELS[label], _one_line(block[0]), " | ".join(block))
                found.setdefault("_addresses", {})[BLOCK_LABELS[label]] = ", ".join(block[1:])
            continue

        key = SIMPLE_LABELS.get(label)
        if not key or not value:
            continue
        ev = line.strip()
        if key in ("invoice_date", "lc_date", "shipment_date"):
            d = parse_date(value)
            if d is None:
                warnings.append(f"Could not read the date: {ev}")
            put(key, d, ev)
        elif key == "total":
            total_text = (value, ev)
        else:
            put(key, _one_line(value), ev)

    # total and currency
    row_cur = found.pop("_row_currencies", None)
    found.pop("_addresses", None)
    currencies = set(row_cur or ())
    if total_text:
        mm = MONEY.match(_one_line(total_text[0]))
        if mm:
            put("total_amount", _number(mm.group(2)), total_text[1])
            put("currency", mm.group(1), total_text[1])
            currencies.add(mm.group(1))
        else:
            warnings.append(f"Could not read the total: {total_text[1]}")
    if found["currency"] is None and row_cur:
        put("currency", row_cur[1], found["line_amount"]["evidence"])

    # the invoice must agree with itself
    if len(currencies) > 1:
        warnings.append("More than one currency on the invoice: " + ", ".join(sorted(currencies)))
    q, p, a, t = (found[k]["value"] if found[k] else None
                  for k in ("quantity", "unit_price", "line_amount", "total_amount"))
    if None not in (q, p, a) and q * p != a:
        warnings.append(f"Quantity x unit price ({q} x {p} = {q * p}) is not the line amount ({a}).")
    if None not in (a, t) and a != t:
        warnings.append(f"Line amount ({a}) is not the total ({t}).")

    return {"fields": found, "warnings": warnings}
