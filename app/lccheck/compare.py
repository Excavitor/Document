"""Compare an invoice with the LC (after amendments). Plain Python, no AI.

The LC is the source of truth. Each row says what the LC wants, what the invoice
shows, and one status:

  MATCH            same, or inside the LC tolerance
  MINOR_VARIATION  small typing or abbreviation difference. An officer decides
  MISMATCH         different
  MISSING          the invoice does not show it, but the LC needs it
  NEEDS_REVIEW     the code cannot decide. A person must look

This tool points at differences. It does not accept or refuse documents.
"""
import difflib
import re
from datetime import date
from decimal import Decimal

STATUSES = ["MATCH", "MINOR_VARIATION", "MISMATCH", "MISSING", "NEEDS_REVIEW"]
NAME_MINOR_RATIO = 0.90  # at or above this, a name difference is only a minor variation

ABBREVIATIONS = {"LTD": "LIMITED", "CO": "COMPANY", "CORP": "CORPORATION",
                 "INC": "INCORPORATED", "PVT": "PRIVATE"}
UNIT_ALIASES = {"PIECE": "PIECES", "PCS": "PIECES", "PC": "PIECES", "KG": "KGS",
                "KILOGRAMS": "KGS", "SET": "SETS", "CARTON": "CARTONS",
                "DOZEN": "DOZENS", "METER": "METERS", "MTR": "METERS", "MTRS": "METERS"}
UNIT_WORDS = "PIECES|PIECE|PCS|PC|SETS|SET|KGS|KG|KILOGRAMS|DOZENS|DOZEN|CARTONS|CARTON|METERS|METER|MTRS|MTR|YARDS|UNITS"

QTY_IN_LC = re.compile(rf"(\d[\d,]*(?:\.\d+)?)\s*({UNIT_WORDS})\b")
PRICE_IN_LC = re.compile(r"PRICE\s+([A-Z]{3})\s*(\d[\d,]*(?:\.\d+)?)\s+PER\s+([A-Z]+)")
TERMS_IN_LC = re.compile(r"\b(CIF|CFR|CIP|CPT|FOB|FCA|FAS|EXW|DAP|DPU|DDP)\b\s*([A-Z ,]*?)\s*(?:[.;]|$)")


# ---------- small helpers ----------

def _fmt(v):
    if v is None:
        return None
    if isinstance(v, date):
        return f"{v.day:02d} {v.strftime('%b %Y')}"
    if isinstance(v, Decimal):
        return f"{v:,}"
    return str(v)


def _get(invoice, name):
    f = invoice["fields"].get(name)
    return (f["value"], f["evidence"]) if f else (None, None)


def _num(text):
    return Decimal(text.replace(",", ""))


def _name_key(text):
    text = text.upper().replace("&", " AND ")
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", text).split())


def _expand(key):
    return " ".join(ABBREVIATIONS.get(t, t) for t in key.split())


def _unit(u):
    u = u.upper()
    return UNIT_ALIASES.get(u, u)


def _tokens(text):
    text = text.upper().replace("'", "")
    return [t for t in re.split(r"[^A-Z0-9-]+", text) if t]


def compare_names(lc_text, doc_text):
    """Return (status, note)."""
    a, b = _name_key(lc_text), _name_key(doc_text)
    if a == b:
        return "MATCH", ""
    ea, eb = _expand(a), _expand(b)
    if ea == eb:
        return "MINOR_VARIATION", "Only an abbreviation differs (for example LTD and LIMITED)."
    ratio = difflib.SequenceMatcher(None, ea, eb).ratio()
    if ratio >= NAME_MINOR_RATIO:
        return "MINOR_VARIATION", f"Very close but not identical (similarity {ratio:.0%})."
    return "MISMATCH", f"Different (similarity {ratio:.0%})."


# ---------- the comparison ----------

def compare_invoice(lc, invoice):
    results, skipped = [], []
    warnings = list(invoice["warnings"])

    def row(field, label, status, tag, lc_value, doc_value, evidence=None, note=""):
        results.append({
            "field": field, "label": label, "status": status, "lc_tag": tag,
            "lc_value": _fmt(lc_value), "doc_value": _fmt(doc_value),
            "evidence": evidence, "note": note,
        })

    def skip(field, reason):
        skipped.append({"field": field, "reason": reason})

    goods = lc.get("goods_description", "")
    conds = " ".join(lc.get("additional_conditions", []) + lc.get("documents_required", [])).upper()
    need_lc_no = "LC NUMBER" in conds or "L/C NUMBER" in conds
    need_lc_date = "LC DATE" in conds or "L/C DATE" in conds

    # --- LC number and date on the invoice ---
    doc, ev = _get(invoice, "lc_number")
    if doc is None:
        if need_lc_no:
            row("lc_number", "LC number", "MISSING", "47A", lc["lc_number"], None,
                note="The LC says the invoice must show the LC number.")
        else:
            skip("lc_number", "not shown, and the LC does not require it")
    else:
        same = re.sub(r"[^A-Z0-9]", "", doc.upper()) == re.sub(r"[^A-Z0-9]", "", lc["lc_number"].upper())
        row("lc_number", "LC number", "MATCH" if same else "MISMATCH", "20", lc["lc_number"], doc, ev)

    doc, ev = _get(invoice, "lc_date")
    if doc is None:
        if need_lc_date:
            row("lc_date", "LC date", "MISSING", "47A", lc.get("issue_date"), None,
                note="The LC says the invoice must show the LC date.")
        else:
            skip("lc_date", "not shown, and the LC does not require it")
    elif lc.get("issue_date") is None:
        row("lc_date", "LC date", "NEEDS_REVIEW", "31C", None, doc, ev, "The LC has no issue date (tag 31C).")
    else:
        row("lc_date", "LC date", "MATCH" if doc == lc["issue_date"] else "MISMATCH",
            "31C", lc["issue_date"], doc, ev)

    # --- parties ---
    for field, label, lc_party, tag in (("buyer_name", "Buyer", "applicant", "50"),
                                        ("seller_name", "Seller", "beneficiary", "59")):
        doc, ev = _get(invoice, "buyer" if field == "buyer_name" else "seller")
        lc_name = lc[lc_party]["name"]
        if doc is None:
            row(field, label, "MISSING", tag, lc_name, None)
        else:
            status, note = compare_names(lc_name, doc)
            row(field, label, status, tag, lc_name, doc, ev, note)

    # --- currency, amount, unit price ---
    cur, ev = _get(invoice, "currency")
    currency_ok = cur == lc["currency"]
    if cur is None:
        row("currency", "Currency", "MISSING", "32B", lc["currency"], None)
        currency_ok = False
    else:
        row("currency", "Currency", "MATCH" if currency_ok else "MISMATCH", "32B", lc["currency"], cur, ev)

    plus = Decimal(lc.get("tolerance_plus_percent") or 0)
    minus = Decimal(lc.get("tolerance_minus_percent") or 0)
    tol_text = f"+{plus}% / -{minus}%"

    def in_range(value, base):
        low, high = base * (100 - minus) / 100, base * (100 + plus) / 100
        return low, high, low <= value <= high

    doc, ev = _get(invoice, "total_amount")
    if doc is None:
        doc, ev = _get(invoice, "line_amount")
    if not currency_ok:
        skip("amount", "not compared because the currency is missing or different")
    elif doc is None:
        row("amount", "Amount", "MISSING", "32B", lc["amount"], None)
    else:
        low, high, ok = in_range(doc, lc["amount"])
        if ok:
            note = "" if doc == lc["amount"] else f"Inside the LC tolerance ({tol_text}, up to {_fmt(high)})."
            row("amount", "Amount", "MATCH", "32B/39A", lc["amount"], doc, ev, note)
        else:
            row("amount", "Amount", "MISMATCH", "32B/39A", lc["amount"], doc, ev,
                f"Outside the LC tolerance ({tol_text}): allowed {_fmt(low)} to {_fmt(high)}. "
                "Earlier drawings are not known to this tool.")

    # --- quantity ---
    q = QTY_IN_LC.search(goods.upper())
    doc_q, ev = _get(invoice, "quantity")
    doc_u, _ = _get(invoice, "unit")
    if q is None:
        row("quantity", "Quantity", "NEEDS_REVIEW", "45A", None, doc_q, ev, "Could not read a quantity from tag 45A.")
    else:
        lc_q, lc_u = _num(q.group(1)), _unit(q.group(2))
        lc_show = f"{_fmt(lc_q)} {lc_u}"
        if doc_q is None:
            row("quantity", "Quantity", "MISSING", "45A", lc_show, None)
        else:
            doc_show = f"{_fmt(doc_q)} {doc_u or ''}".strip()
            low, high, ok = in_range(doc_q, lc_q)
            if doc_u and _unit(doc_u) != lc_u:
                row("quantity", "Quantity", "MISMATCH", "45A", lc_show, doc_show, ev, "The unit is different.")
            elif ok:
                note = "" if doc_q == lc_q else f"Inside the LC tolerance ({tol_text}, up to {_fmt(high)})."
                row("quantity", "Quantity", "MATCH", "45A/39A", lc_show, doc_show, ev, note)
            else:
                row("quantity", "Quantity", "MISMATCH", "45A/39A", lc_show, doc_show, ev,
                    f"Outside the LC tolerance ({tol_text}): allowed {_fmt(low)} to {_fmt(high)}.")

    p = PRICE_IN_LC.search(goods.upper())
    if p:
        lc_price = _num(p.group(2))
        lc_show = f"{p.group(1)} {_fmt(lc_price)} per {p.group(3).lower()}"
        doc, ev = _get(invoice, "unit_price")
        if not currency_ok:
            skip("unit_price", "not compared because the currency is missing or different")
        elif doc is None:
            row("unit_price", "Unit price", "MISSING", "45A", lc_show, None)
        else:
            row("unit_price", "Unit price", "MATCH" if doc == lc_price else "MISMATCH",
                "45A", lc_show, f"{cur} {_fmt(doc)}", ev)

    # --- goods description ---
    doc, ev = _get(invoice, "goods_description")
    if not goods:
        row("goods_description", "Goods", "NEEDS_REVIEW", "45A", None, doc, ev, "The LC has no goods text.")
    elif doc is None:
        row("goods_description", "Goods", "MISSING", "45A", goods, None)
    else:
        core = re.sub(r"^\s*\d[\d,]*\s+\w+\s+(OF\s+)?", "", goods.upper())
        core = re.split(r"\b(?:AS PER|PRICE)\b", core)[0]
        core_tokens, all_tokens = set(_tokens(core)), set(_tokens(goods))
        doc_tokens = set(_tokens(doc))
        missing = sorted(core_tokens - doc_tokens)
        extra = sorted(doc_tokens - all_tokens)
        if not missing and not extra:
            row("goods_description", "Goods", "MATCH", "45A", goods, doc, ev)
        else:
            parts = []
            if extra:
                parts.append("Words on the invoice that are not in the LC: " + ", ".join(extra) + ".")
            if missing:
                parts.append("LC goods words not on the invoice: " + ", ".join(missing) + ".")
            status = "MISMATCH" if (missing and extra) else "NEEDS_REVIEW"
            row("goods_description", "Goods", status, "45A", goods, doc, ev, " ".join(parts))

    # --- ports ---
    for field, label, key, tag in (("port_of_loading", "Port of loading", "port_of_loading", "44E"),
                                   ("port_of_discharge", "Port of discharge", "port_of_discharge", "44F")):
        lc_val = lc.get(key)
        if not lc_val:
            skip(field, "the LC does not name one")
            continue
        doc, ev = _get(invoice, key)
        if "ANY" in _tokens(lc_val):
            row(field, label, "NEEDS_REVIEW", tag, lc_val, doc, ev, "The LC allows a choice. A person must check.")
        elif doc is None:
            row(field, label, "MISSING", tag, lc_val, None)
        else:
            status, note = compare_names(lc_val, doc)
            row(field, label, status, tag, lc_val, doc, ev, note)

    # --- delivery terms ---
    t = TERMS_IN_LC.search(" ".join(goods.upper().split()))
    if t:
        lc_terms = (t.group(1) + " " + t.group(2)).strip(" ,")
        doc, ev = _get(invoice, "terms")
        if doc is None:
            row("terms", "Delivery terms", "MISSING", "45A", lc_terms, None)
        else:
            row("terms", "Delivery terms", "MATCH" if _name_key(doc) == _name_key(lc_terms) else "MISMATCH",
                "45A", lc_terms, doc, ev)

    # --- shipment date ---
    latest, expiry = lc.get("latest_shipment_date"), lc.get("expiry_date")
    doc, ev = _get(invoice, "shipment_date")
    if latest is None:
        skip("shipment_date", "the LC has no latest shipment date")
    elif doc is None:
        skip("shipment_date", "the invoice shows no shipment date. Check the bill of lading")
    else:
        late = (doc - latest).days
        note = ""
        status = "MATCH"
        if late > 0:
            status, note = "MISMATCH", f"{late} day(s) after the latest shipment date."
        if expiry and doc > expiry:
            status, note = "MISMATCH", (note + " " if note else "") + "After the LC expiry date."
        note += (" " if note else "") + "The bill of lading date is the real proof of shipment."
        row("shipment_date", "Shipment date", status, "44C", f"latest {_fmt(latest)}", doc, ev, note)

    # --- things only a person can read ---
    for a in lc.get("amendments", []):
        if a["narrative"]:
            warnings.append(f"Amendment {a['number']} has free text (tag 79). A person must read it: "
                            + " ".join(a["narrative"]))

    summary = {s: sum(1 for r in results if r["status"] == s) for s in STATUSES}
    return {"results": results, "skipped": skipped, "warnings": warnings, "summary": summary}
