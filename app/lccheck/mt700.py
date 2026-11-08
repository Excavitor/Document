"""Read a SWIFT MT700 (LC) and MT707 (amendment) from plain text.

Plain Python. No AI, no Django. Every value is read by its tag number,
so the result is always the same for the same input.
"""
import copy
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

TAG_LINE = re.compile(r"^:(\d{2}[A-Z]?):(.*)$")


class LCParseError(Exception):
    pass


# ---------- step 1: text -> {tag: text} ----------

def split_tags(text):
    """Lines before the first tag are ignored. Lines without a tag continue the last tag."""
    parts = {}
    current = None
    for line in text.replace("\r", "").split("\n"):
        m = TAG_LINE.match(line.strip())
        if m:
            current = m.group(1)
            parts.setdefault(current, []).append(m.group(2))
        elif current is not None:
            parts[current][-1] += "\n" + line
    return {tag: "\n".join(v).strip() for tag, v in parts.items()}


# ---------- step 2: small readers for each kind of field ----------

def _one_line(value):
    return " ".join(value.split())


def _date(value):
    value = value.strip()
    try:
        return datetime.strptime(value[:6], "%y%m%d").date()
    except ValueError:
        raise LCParseError(f"Bad date: {value!r}")


def _amount(value):
    m = re.match(r"^([A-Z]{3})\s*([\d.,]+)$", value.strip())
    if not m:
        raise LCParseError(f"Bad amount: {value!r}")
    number = m.group(2).replace(".", "").replace(",", ".")  # SWIFT uses a comma as the decimal sign
    try:
        return m.group(1), Decimal(number)
    except InvalidOperation:
        raise LCParseError(f"Bad amount: {value!r}")


def _party(value):
    lines = [ln.strip() for ln in value.split("\n") if ln.strip()]
    return {"name": lines[0] if lines else "", "address": ", ".join(lines[1:])}


def _plus_items(value):
    """Lines that start with + are separate items. Other lines continue the item above."""
    items = []
    for ln in value.split("\n"):
        ln = ln.strip()
        if not ln:
            continue
        if ln.startswith("+"):
            items.append(ln[1:].strip())
        elif items:
            items[-1] += " " + ln
        else:
            items.append(ln)
    return items


def parse_tag(tag, value):
    """Return {field_name: value} for one tag, or {} if we do not read that tag yet."""
    if tag == "20":
        return {"lc_number": _one_line(value)}
    if tag == "31C":
        return {"issue_date": _date(value)}
    if tag == "31D":
        return {"expiry_date": _date(value), "expiry_place": _one_line(value[6:])}
    if tag == "50":
        return {"applicant": _party(value)}
    if tag == "59":
        return {"beneficiary": _party(value)}
    if tag in ("32B", "34B"):
        currency, amount = _amount(value)
        return {"currency": currency, "amount": amount}
    if tag == "39A":
        m = re.match(r"^(\d{1,2})\s*/\s*(\d{1,2})$", value.strip())
        if not m:
            raise LCParseError(f"Bad tolerance: {value!r}")
        return {"tolerance_plus_percent": int(m.group(1)), "tolerance_minus_percent": int(m.group(2))}
    if tag == "43P":
        return {"partial_shipments": _one_line(value)}
    if tag == "43T":
        return {"transshipment": _one_line(value)}
    if tag == "44E":
        return {"port_of_loading": _one_line(value)}
    if tag == "44F":
        return {"port_of_discharge": _one_line(value)}
    if tag == "44C":
        return {"latest_shipment_date": _date(value)}
    if tag == "45A":
        return {"goods_description": _one_line(value)}
    if tag == "46A":
        return {"documents_required": _plus_items(value)}
    if tag == "47A":
        return {"additional_conditions": _plus_items(value)}
    if tag == "48":
        m = re.match(r"^(\d+)", value.strip())
        return {"presentation_days": int(m.group(1))} if m else {}
    return {}


# ---------- step 3: the whole LC ----------

REQUIRED_TAGS = ["20", "31D", "32B", "50", "59", "45A"]


def parse_mt700(text):
    tags = split_tags(text)
    missing = [t for t in REQUIRED_TAGS if t not in tags]
    if missing:
        raise LCParseError("Missing required tag(s): " + ", ".join(missing))
    lc = {}
    for tag, value in tags.items():
        lc.update(parse_tag(tag, value))
    lc["raw_tags"] = tags
    lc["amendments"] = []
    return lc


# ---------- step 4: apply an MT707 amendment ----------

def parse_mt707(text):
    tags = split_tags(text)
    for t in ("21", "26E"):
        if t not in tags:
            raise LCParseError(f"Amendment is missing tag {t}")
    return tags


def apply_mt707(lc, amendment_text):
    """Return a NEW LC with the amendment applied. The original is not changed."""
    tags = parse_mt707(amendment_text)
    if _one_line(tags["21"]) != lc["lc_number"]:
        raise LCParseError(
            f"Amendment is for {_one_line(tags['21'])}, not for {lc['lc_number']}"
        )
    new_lc = copy.deepcopy(lc)
    changes = []

    def set_field(name, new_value):
        old_value = new_lc.get(name)
        if old_value != new_value:
            changes.append({"field": name, "old": old_value, "new": new_value})
            new_lc[name] = new_value

    for tag, value in tags.items():
        if tag in ("20", "21", "26E", "27", "30", "79", "32B", "33B", "34B"):
            continue  # handled below or not an LC field
        for name, new_value in parse_tag(tag, value).items():
            set_field(name, new_value)

    # Amount: 34B = new total. 32B = increase. 33B = decrease.
    if "34B" in tags:
        _, total = _amount(tags["34B"])
        set_field("amount", total)
    elif "32B" in tags:
        _, extra = _amount(tags["32B"])
        set_field("amount", new_lc["amount"] + extra)
    elif "33B" in tags:
        _, less = _amount(tags["33B"])
        set_field("amount", new_lc["amount"] - less)

    narrative = _plus_items(tags["79"]) if "79" in tags else []
    new_lc["amendments"].append({
        "number": int(re.match(r"\d+", tags["26E"]).group()),
        "date": _date(tags["30"]) if "30" in tags else None,
        "changes": changes,
        # Free text (tag 79) can change goods or documents. A person must read it.
        "narrative": narrative,
    })
    return new_lc
