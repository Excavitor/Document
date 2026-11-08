import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from lccheck.mt700 import LCParseError, apply_mt707, parse_mt700, split_tags

DATA = Path(__file__).resolve().parents[2] / "testdata" / "lc"


def read(name):
    return (DATA / name).read_text(encoding="utf-8")


class ParseMT700(unittest.TestCase):
    def setUp(self):
        self.lc = parse_mt700(read("mt700_lc2026100045.txt"))

    def test_basic_fields(self):
        lc = self.lc
        self.assertEqual(lc["lc_number"], "LC2026100045")
        self.assertEqual(lc["issue_date"], date(2026, 10, 1))
        self.assertEqual(lc["expiry_date"], date(2027, 1, 15))
        self.assertEqual(lc["expiry_place"], "DHAKA, BANGLADESH")
        self.assertEqual(lc["currency"], "USD")
        self.assertEqual(lc["amount"], Decimal("125000.00"))
        self.assertEqual(lc["tolerance_plus_percent"], 5)
        self.assertEqual(lc["tolerance_minus_percent"], 5)
        self.assertEqual(lc["latest_shipment_date"], date(2026, 12, 15))
        self.assertEqual(lc["presentation_days"], 21)

    def test_parties(self):
        self.assertEqual(self.lc["applicant"]["name"], "NORTHSTAR IMPORTS LTD")
        self.assertEqual(self.lc["beneficiary"]["name"], "BENGAL KNITWEAR LIMITED")
        self.assertIn("UTTARA", self.lc["beneficiary"]["address"])

    def test_ports_and_shipment_rules(self):
        self.assertEqual(self.lc["port_of_loading"], "CHITTAGONG, BANGLADESH")
        self.assertEqual(self.lc["port_of_discharge"], "FELIXSTOWE, UNITED KINGDOM")
        self.assertEqual(self.lc["partial_shipments"], "NOT ALLOWED")

    def test_goods_and_lists(self):
        self.assertIn("100 PERCENT COTTON", self.lc["goods_description"])
        self.assertIn("5000 PIECES", self.lc["goods_description"])
        self.assertEqual(len(self.lc["documents_required"]), 4)
        self.assertEqual(len(self.lc["additional_conditions"]), 2)
        # a line that continues the previous item stays in the same item
        self.assertIn("NOTIFY APPLICANT", self.lc["documents_required"][1])

    def test_text_before_first_tag_is_ignored(self):
        tags = split_tags("HEADER LINE\n:20:ABC\n:59:X\nY")
        self.assertEqual(tags, {"20": "ABC", "59": "X\nY"})

    def test_missing_required_tag(self):
        with self.assertRaises(LCParseError):
            parse_mt700(":20:ABC\n:32B:USD100,00")

    def test_bad_amount(self):
        text = read("mt700_lc2026100045.txt").replace("USD125000,00", "USDabc")
        with self.assertRaises(LCParseError):
            parse_mt700(text)


class ApplyMT707(unittest.TestCase):
    def setUp(self):
        self.lc = parse_mt700(read("mt700_lc2026100045.txt"))
        self.amd = read("mt707_amendment_1.txt")

    def test_shipment_date_changes(self):
        new_lc = apply_mt707(self.lc, self.amd)
        self.assertEqual(new_lc["latest_shipment_date"], date(2026, 12, 30))
        self.assertEqual(len(new_lc["amendments"]), 1)
        change = new_lc["amendments"][0]["changes"][0]
        self.assertEqual(change["field"], "latest_shipment_date")
        self.assertEqual(change["old"], date(2026, 12, 15))

    def test_original_is_not_changed(self):
        apply_mt707(self.lc, self.amd)
        self.assertEqual(self.lc["latest_shipment_date"], date(2026, 12, 15))
        self.assertEqual(self.lc["amendments"], [])

    def test_narrative_is_kept_for_the_officer(self):
        new_lc = apply_mt707(self.lc, self.amd)
        self.assertEqual(len(new_lc["amendments"][0]["narrative"]), 2)

    def test_wrong_lc_number_is_refused(self):
        with self.assertRaises(LCParseError):
            apply_mt707(self.lc, self.amd.replace("LC2026100045", "LC9999999999"))

    def test_amount_increase_and_total(self):
        up = self.amd + ":32B:USD5000,00\n"
        self.assertEqual(apply_mt707(self.lc, up)["amount"], Decimal("130000.00"))
        total = self.amd + ":34B:USD140000,00\n"
        self.assertEqual(apply_mt707(self.lc, total)["amount"], Decimal("140000.00"))


if __name__ == "__main__":
    unittest.main()
