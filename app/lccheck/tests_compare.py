import copy
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from lccheck import evaluate
from lccheck.compare import compare_invoice, compare_names
from lccheck.invoice import parse_invoice
from lccheck.mt700 import apply_mt707, parse_mt700

DATA = Path(__file__).resolve().parents[2] / "testdata" / "lc"


def read(name):
    return (DATA / name).read_text(encoding="utf-8")


LC = parse_mt700(read("mt700_lc2026100045.txt"))
OK = parse_invoice(read("invoice_ok.txt"))


def changed(invoice, **values):
    """Copy of the invoice with some field values replaced."""
    inv = copy.deepcopy(invoice)
    for name, value in values.items():
        if value is None:
            inv["fields"][name] = None
        else:
            inv["fields"][name] = {"value": value, "evidence": f"test: {name}"}
    return inv


def status(result, field):
    for r in result["results"]:
        if r["field"] == field:
            return r["status"]
    return None


class AnswerKey(unittest.TestCase):
    def test_everything_in_the_answer_key_is_found(self):
        _, problems, totals = evaluate.run()
        self.assertEqual(problems, [])
        self.assertEqual(totals["false_alarms"], 0)
        self.assertEqual(totals["missed"], 0)


class Tolerance(unittest.TestCase):
    def test_amount_at_the_limit(self):
        r = compare_invoice(LC, changed(OK, total_amount=Decimal("131250.00")))
        self.assertEqual(status(r, "amount"), "MATCH")
        r = compare_invoice(LC, changed(OK, total_amount=Decimal("131250.01")))
        self.assertEqual(status(r, "amount"), "MISMATCH")
        r = compare_invoice(LC, changed(OK, total_amount=Decimal("118750.00")))
        self.assertEqual(status(r, "amount"), "MATCH")
        r = compare_invoice(LC, changed(OK, total_amount=Decimal("118749.99")))
        self.assertEqual(status(r, "amount"), "MISMATCH")

    def test_quantity_at_the_limit(self):
        self.assertEqual(status(compare_invoice(LC, changed(OK, quantity=Decimal("5250"))), "quantity"), "MATCH")
        self.assertEqual(status(compare_invoice(LC, changed(OK, quantity=Decimal("5251"))), "quantity"), "MISMATCH")

    def test_different_unit(self):
        r = compare_invoice(LC, changed(OK, unit="KGS"))
        self.assertEqual(status(r, "quantity"), "MISMATCH")

    def test_no_tolerance_in_lc_means_exact(self):
        lc = copy.deepcopy(LC)
        lc["tolerance_plus_percent"] = lc["tolerance_minus_percent"] = None
        r = compare_invoice(lc, changed(OK, total_amount=Decimal("125000.01")))
        self.assertEqual(status(r, "amount"), "MISMATCH")


class Currency(unittest.TestCase):
    def test_wrong_currency_skips_amount(self):
        r = compare_invoice(LC, changed(OK, currency="EUR"))
        self.assertEqual(status(r, "currency"), "MISMATCH")
        self.assertIsNone(status(r, "amount"))
        self.assertIn("amount", [s["field"] for s in r["skipped"]])

    def test_unit_price_difference(self):
        r = compare_invoice(LC, changed(OK, unit_price=Decimal("24.00")))
        self.assertEqual(status(r, "unit_price"), "MISMATCH")


class Names(unittest.TestCase):
    def test_exact_after_case_and_punctuation(self):
        self.assertEqual(compare_names("NORTHSTAR IMPORTS LTD", "Northstar Imports Ltd.")[0], "MATCH")

    def test_abbreviation(self):
        self.assertEqual(compare_names("NORTHSTAR IMPORTS LTD", "NORTHSTAR IMPORTS LIMITED")[0], "MINOR_VARIATION")

    def test_typo(self):
        self.assertEqual(compare_names("NORTHSTAR IMPORTS LTD", "NORTHSTAR IMPORT LTD")[0], "MINOR_VARIATION")

    def test_different_company(self):
        self.assertEqual(compare_names("NORTHSTAR IMPORTS LTD", "SOUTHWIND TRADING LTD")[0], "MISMATCH")
        self.assertEqual(compare_names("NORTHSTAR IMPORTS LTD", "NORTHSTAR TRADING LTD")[0], "MISMATCH")

    def test_missing_buyer(self):
        self.assertEqual(status(compare_invoice(LC, changed(OK, buyer=None)), "buyer_name"), "MISSING")


class Goods(unittest.TestCase):
    def test_shorter_description_needs_review(self):
        r = compare_invoice(LC, changed(OK, goods_description="MEN'S COTTON KNITTED T-SHIRTS"))
        self.assertEqual(status(r, "goods_description"), "NEEDS_REVIEW")

    def test_extra_word_needs_review(self):
        r = compare_invoice(LC, changed(OK, goods_description=OK["fields"]["goods_description"]["value"] + " WITH LOGO"))
        self.assertEqual(status(r, "goods_description"), "NEEDS_REVIEW")

    def test_changed_material_is_mismatch(self):
        inv = parse_invoice(read("invoice_b_errors.txt"))
        self.assertEqual(status(compare_invoice(LC, inv), "goods_description"), "MISMATCH")


class Dates(unittest.TestCase):
    def test_shipment_on_the_last_day(self):
        self.assertEqual(status(compare_invoice(LC, changed(OK, shipment_date=date(2026, 12, 15))), "shipment_date"), "MATCH")
        self.assertEqual(status(compare_invoice(LC, changed(OK, shipment_date=date(2026, 12, 16))), "shipment_date"), "MISMATCH")

    def test_amendment_moves_the_last_day(self):
        amended = apply_mt707(LC, read("mt707_amendment_1.txt"))
        inv = changed(OK, shipment_date=date(2026, 12, 20))
        self.assertEqual(status(compare_invoice(LC, inv), "shipment_date"), "MISMATCH")
        self.assertEqual(status(compare_invoice(amended, inv), "shipment_date"), "MATCH")

    def test_after_expiry(self):
        r = compare_invoice(LC, changed(OK, shipment_date=date(2027, 2, 1)))
        self.assertIn("expiry", [x for x in r["results"] if x["field"] == "shipment_date"][0]["note"])

    def test_no_shipment_date_is_skipped_not_missing(self):
        r = compare_invoice(LC, changed(OK, shipment_date=None))
        self.assertIsNone(status(r, "shipment_date"))
        self.assertIn("shipment_date", [s["field"] for s in r["skipped"]])


class LcReference(unittest.TestCase):
    def test_missing_when_required(self):
        r = compare_invoice(LC, changed(OK, lc_number=None, lc_date=None))
        self.assertEqual(status(r, "lc_number"), "MISSING")
        self.assertEqual(status(r, "lc_date"), "MISSING")

    def test_not_reported_when_not_required(self):
        lc = copy.deepcopy(LC)
        lc["additional_conditions"] = []
        r = compare_invoice(lc, changed(OK, lc_number=None, lc_date=None))
        self.assertIsNone(status(r, "lc_number"))
        self.assertIsNone(status(r, "lc_date"))

    def test_spaces_and_dashes_are_ignored(self):
        r = compare_invoice(LC, changed(OK, lc_number="LC 2026-100045"))
        self.assertEqual(status(r, "lc_number"), "MATCH")


class OtherRules(unittest.TestCase):
    def test_any_port_needs_review(self):
        lc = copy.deepcopy(LC)
        lc["port_of_loading"] = "ANY PORT IN BANGLADESH"
        self.assertEqual(status(compare_invoice(lc, OK), "port_of_loading"), "NEEDS_REVIEW")

    def test_different_port(self):
        r = compare_invoice(LC, changed(OK, port_of_discharge="ROTTERDAM, NETHERLANDS"))
        self.assertEqual(status(r, "port_of_discharge"), "MISMATCH")

    def test_terms(self):
        r = compare_invoice(LC, changed(OK, terms="FOB CHITTAGONG"))
        self.assertEqual(status(r, "terms"), "MISMATCH")

    def test_amendment_text_is_flagged_for_a_person(self):
        amended = apply_mt707(LC, read("mt707_amendment_1.txt"))
        r = compare_invoice(amended, OK)
        self.assertTrue(any("must read it" in w for w in r["warnings"]))

    def test_summary_counts(self):
        r = compare_invoice(LC, parse_invoice(read("invoice_a_errors.txt")))
        self.assertEqual(r["summary"]["MINOR_VARIATION"], 1)
        self.assertEqual(r["summary"]["MISMATCH"], 2)


if __name__ == "__main__":
    unittest.main()
