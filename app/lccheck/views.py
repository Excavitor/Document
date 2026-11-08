import json
from pathlib import Path

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from .compare import STATUSES, _fmt, compare_invoice
from .invoice import parse_invoice
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
    return JsonResponse(result)
