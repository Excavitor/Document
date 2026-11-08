import json
from pathlib import Path

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from .compare import STATUSES, _fmt, compare_invoice
from .explain import generate_explanation
from .invoice import parse_invoice
from .models import OfficerDecision
from .mt700 import LCParseError, apply_mt707, parse_mt700

MAX_CHARS = 100_000      # per pasted text
MAX_AMENDMENTS = 10

# Synthetic test files only. The page never opens any other file.
SAMPLE_DIR = Path(settings.BASE_DIR).parent / "testdata" / "lc"
SAMPLES = {
    "lc": "mt700_lc2026100045.txt",
    "amendment": "mt707_amendment_1.txt",
    "invoice_ok": "invoice_ok.txt",
    "invoice_a": "invoice_a_errors.txt",
    "invoice_b": "invoice_b_errors.txt",
}

VALID_DECISIONS = {"", "ACCEPT", "REFER", "REJECT"}


def _error(message, status=400):
    return JsonResponse({"error": message}, status=status)


def check_page(request):
    return render(request, "lccheck/check.html")


@require_GET
def sample(request):
    filename = SAMPLES.get(request.GET.get("name", ""))
    path = SAMPLE_DIR / filename if filename else None
    if path is None or not path.is_file():
        return _error("Sample not found.", 404)
    return JsonResponse({"text": path.read_text(encoding="utf-8")})


def _lc_info(lc):
    return {
        "lc_number": lc["lc_number"],
        "amount": f"{lc['currency']} {_fmt(lc['amount'])}",
        "applicant": lc["applicant"]["name"],
        "beneficiary": lc["beneficiary"]["name"],
        "latest_shipment": _fmt(lc.get("latest_shipment_date")),
        "expiry": _fmt(lc.get("expiry_date")),
        "amendments": [
            {
                "number": a["number"],
                "changes": [f"{c['field']}: {_fmt(c['old'])} -> {_fmt(c['new'])}" for c in a["changes"]],
            }
            for a in lc["amendments"]
        ],
    }


@require_POST
def api_check(request):
    try:
        body = json.loads(request.body)
    except ValueError:
        return _error("Bad request.")

    lc_text = (body.get("lc") or "").strip()
    invoice_text = (body.get("invoice") or "").strip()
    raw_amendments = body.get("amendments") or []
    if not isinstance(raw_amendments, list):
        return _error("Bad request.")
    amendments = [a.strip() for a in raw_amendments if isinstance(a, str) and a.strip()]

    if not lc_text:
        return _error("Paste the LC text on the left.")
    if not invoice_text:
        return _error("Paste the invoice text on the right.")
    if len(amendments) > MAX_AMENDMENTS:
        return _error(f"At most {MAX_AMENDMENTS} amendments.")
    if any(len(t) > MAX_CHARS for t in [lc_text, invoice_text, *amendments]):
        return _error("One of the texts is too long.")

    try:
        lc = parse_mt700(lc_text)
    except LCParseError as exc:
        return _error(f"LC problem: {exc}")
    for number, text in enumerate(amendments, 1):
        try:
            lc = apply_mt707(lc, text)
        except LCParseError as exc:
            return _error(f"Amendment {number} problem: {exc}")

    invoice = parse_invoice(invoice_text)
    if all(v is None for v in invoice["fields"].values()):
        return _error("Nothing could be read from the invoice. "
                      "This version needs lines like \"Invoice No: ...\" and \"Letter of Credit No: ...\".")

    result = compare_invoice(lc, invoice)
    result["error"] = None
    result["lc_info"] = _lc_info(lc)
    result["statuses"] = STATUSES

    # Look up previously saved officer decisions for this LC & invoice pair
    lc_num = lc.get("lc_number", "")
    inv_num = (invoice["fields"].get("invoice_number") or {}).get("value") or ""
    result["invoice_info"] = {"invoice_number": inv_num}

    saved_decisions = {
        d.field: {
            "decision": d.decision,
            "comment": d.comment,
            "ai_explanation": d.ai_explanation,
        }
        for d in OfficerDecision.objects.filter(lc_number=lc_num, invoice_number=inv_num)
    }

    decision_summary = {"ACCEPT": 0, "REFER": 0, "REJECT": 0, "PENDING": 0}
    for r in result["results"]:
        saved = saved_decisions.get(r["field"])
        r["decision"] = saved["decision"] if saved else ""
        r["comment"] = saved["comment"] if saved else ""
        r["ai_explanation"] = saved["ai_explanation"] if saved else ""
        if r["status"] != "MATCH":
            if r["decision"] in decision_summary:
                decision_summary[r["decision"]] += 1
            else:
                decision_summary["PENDING"] += 1

    result["decision_summary"] = decision_summary
    return JsonResponse(result)


@require_POST
def api_decision(request):
    """Save an officer's decision and comment for a finding."""
    try:
        body = json.loads(request.body)
    except ValueError:
        return _error("Bad request.")

    lc_number = (body.get("lc_number") or "").strip()
    invoice_number = (body.get("invoice_number") or "").strip()
    field = (body.get("field") or "").strip()
    decision = (body.get("decision") or "").strip().upper()
    comment = (body.get("comment") or "").strip()
    ai_explanation = (body.get("ai_explanation") or "").strip()

    if not lc_number or not field:
        return _error("lc_number and field are required.")
    if decision not in VALID_DECISIONS:
        return _error(f"Invalid decision '{decision}'. Must be one of: ACCEPT, REFER, REJECT, or empty.")

    record, _ = OfficerDecision.objects.update_or_create(
        lc_number=lc_number,
        invoice_number=invoice_number,
        field=field,
        defaults={
            "decision": decision,
            "comment": comment,
            "ai_explanation": ai_explanation,
        },
    )

    return JsonResponse({
        "status": "ok",
        "lc_number": record.lc_number,
        "invoice_number": record.invoice_number,
        "field": record.field,
        "decision": record.decision,
        "comment": record.comment,
        "ai_explanation": record.ai_explanation,
        "updated_at": record.updated_at.isoformat(),
    })


@require_POST
def api_explain(request):
    """Generate an AI explanation for a finding using the local model."""
    try:
        body = json.loads(request.body)
    except ValueError:
        return _error("Bad request.")

    field_info = body.get("field_info") or body
    field = (field_info.get("field") or "").strip()
    if not field:
        return _error("field is required.")

    result = generate_explanation(field_info)

    # If explanation succeeded and lc_number is provided, persist it in OfficerDecision
    lc_number = (field_info.get("lc_number") or "").strip()
    invoice_number = (field_info.get("invoice_number") or "").strip()
    if result["explanation"] and lc_number:
        OfficerDecision.objects.update_or_create(
            lc_number=lc_number,
            invoice_number=invoice_number,
            field=field,
            defaults={"ai_explanation": result["explanation"]},
        )

    return JsonResponse(result)
