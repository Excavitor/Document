"""Print what the parser reads. Run from the app folder:  python -m lccheck.demo_parse"""
from pathlib import Path

from lccheck.mt700 import apply_mt707, parse_mt700

DATA = Path(__file__).resolve().parents[2] / "testdata" / "lc"


def show(title, lc):
    print("=" * 60)
    print(title)
    print("=" * 60)
    for key, value in lc.items():
        if key in ("raw_tags", "amendments"):
            continue
        if isinstance(value, list):
            print(f"{key}:")
            for item in value:
                print(f"   - {item}")
        else:
            print(f"{key}: {value}")


lc = parse_mt700((DATA / "mt700_lc2026100045.txt").read_text(encoding="utf-8"))
show("LC as issued", lc)

amended = apply_mt707(lc, (DATA / "mt707_amendment_1.txt").read_text(encoding="utf-8"))
print()
print("Amendment 1 changed:")
for c in amended["amendments"][0]["changes"]:
    print(f"   {c['field']}: {c['old']}  ->  {c['new']}")
print("Narrative for the officer to read:")
for line in amended["amendments"][0]["narrative"]:
    print(f"   - {line}")
