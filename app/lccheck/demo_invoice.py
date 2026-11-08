"""Print what the invoice reader finds. Run from the app folder:  python -m lccheck.demo_invoice"""
from pathlib import Path

from lccheck.invoice import parse_invoice

DATA = Path(__file__).resolve().parents[2] / "testdata" / "lc"

for name in ("invoice_ok.txt", "invoice_a_errors.txt", "invoice_b_errors.txt"):
    result = parse_invoice((DATA / name).read_text(encoding="utf-8"))
    print("=" * 70)
    print(name)
    print("=" * 70)
    for field, item in result["fields"].items():
        if item is None:
            print(f"{field:20} NOT FOUND")
        else:
            print(f"{field:20} {item['value']}")
    for w in result["warnings"]:
        print("WARNING:", w)
    print()
