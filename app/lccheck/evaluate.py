"""Run the checker on the test invoices and compare with answer_key.json.
Run from the app folder:  python -m lccheck.evaluate
"""
import json
from pathlib import Path

from lccheck.compare import compare_invoice
from lccheck.invoice import parse_invoice
from lccheck.mt700 import apply_mt707, parse_mt700

DATA = Path(__file__).resolve().parents[2] / "testdata" / "lc"


def _read(name):
    return (DATA / name).read_text(encoding="utf-8")


def run():
    """Return (lines_to_print, problems, totals)."""
    key = json.loads(_read("answer_key.json"))
    lc0 = parse_mt700(_read(key["lc"]))
    lc1 = apply_mt707(lc0, _read(key["amendment"]))
    lines, problems = [], []
    tp = fp = fn = 0

    for case in key["cases"]:
        invoice = parse_invoice(_read(case["file"]))
        without = case["expected_issues_without_amendment"]
        with_ = case["expected_issues_with_amendment"]
        if isinstance(with_, str):
            with_ = without
        for mode, lc, expected in (("without amendment", lc0, without), ("with amendment", lc1, with_)):
            result = compare_invoice(lc, invoice)
            got = {(r["field"], r["status"]) for r in result["results"] if r["status"] != "MATCH"}
            exp = {(i["field"], i["expected_status"]) for i in expected}
            tp += len(got & exp)
            fp += len(got - exp)
            fn += len(exp - got)
            lines.append(f"{case['file']:24} {mode:18} expected {len(exp)}  found {len(got)}  "
                         + ("OK" if got == exp else "DIFFERENT"))
            for f, s in sorted(exp - got):
                problems.append(f"{case['file']} ({mode}): MISSED {f} {s}")
            for f, s in sorted(got - exp):
                problems.append(f"{case['file']} ({mode}): FALSE ALARM {f} {s}")
            by_field = {r["field"]: r["status"] for r in result["results"]}
            for item in case.get("must_not_be_flagged", []):
                if by_field.get(item["field"]) != "MATCH":
                    problems.append(f"{case['file']} ({mode}): {item['field']} should be MATCH, "
                                    f"got {by_field.get(item['field'])}")
    totals = {"correct": tp, "false_alarms": fp, "missed": fn,
              "precision": tp / (tp + fp) if tp + fp else 1.0,
              "recall": tp / (tp + fn) if tp + fn else 1.0}
    return lines, problems, totals


if __name__ == "__main__":
    lines, problems, totals = run()
    print("\n".join(lines))
    print()
    print(f"Correct: {totals['correct']}   False alarms: {totals['false_alarms']}   Missed: {totals['missed']}")
    print(f"Precision: {totals['precision']:.0%}   Recall: {totals['recall']:.0%}")
    for p in problems:
        print("PROBLEM:", p)
