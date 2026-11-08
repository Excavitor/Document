"""Show the full comparison for one invoice. From the app folder:
    python -m lccheck.demo_compare invoice_b_errors.txt
Add the word 'amended' to apply the amendment:
    python -m lccheck.demo_compare invoice_b_errors.txt amended
"""
import sys
from pathlib import Path

from lccheck.compare import compare_invoice
from lccheck.invoice import parse_invoice
from lccheck.mt700 import apply_mt707, parse_mt700

DATA = Path(__file__).resolve().parents[2] / "testdata" / "lc"
name = sys.argv[1] if len(sys.argv) > 1 else "invoice_b_errors.txt"
amended = "amended" in sys.argv[2:]

lc = parse_mt700((DATA / "mt700_lc2026100045.txt").read_text(encoding="utf-8"))
if amended:
    lc = apply_mt707(lc, (DATA / "mt707_amendment_1.txt").read_text(encoding="utf-8"))
result = compare_invoice(lc, parse_invoice((DATA / name).read_text(encoding="utf-8")))

print(f"{name}  ({'with' if amended else 'without'} amendment)")
print("-" * 78)
for r in result["results"]:
    print(f"{r['status']:16} {r['label']}")
    if r["status"] != "MATCH":
        print(f"      LC ({r['lc_tag']}): {r['lc_value']}")
        print(f"      Invoice : {r['doc_value']}")
        if r["note"]:
            print(f"      Note    : {r['note']}")
        if r["evidence"]:
            print(f"      Line    : {r['evidence']}")
print("-" * 78)
print("Summary:", ", ".join(f"{k} {v}" for k, v in result["summary"].items() if v))
for s in result["skipped"]:
    print(f"Not compared: {s['field']} ({s['reason']})")
for w in result["warnings"]:
    print("WARNING:", w)
