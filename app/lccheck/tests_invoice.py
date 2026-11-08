import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from lccheck.invoice import FIELD_NAMES, parse_date, parse_invoice

DATA = Path(__file__).resolve().parents[2] / "testdata" / "lc"


def load(name):
    return parse_invoice((DATA / name).read_text(encoding="utf-8"))


def val(result, name):
    f = result["fields"][name]
    return f["value"] if f else None


class GoodInvoice(unittest.TestCase):
    def setUp(self):
        self.r = load("invoice_ok.txt")

    def test_fields(self):
        v = lambda n: val(self.r, n)
        self.assertEqual(v("invoice_number"), "BKL/INV/2026/0412")
        self.assertEqual(v("invoice_date"), date(2026, 11, 20))
        self.assertEqual(v("seller"), "BENGAL KNITWEAR LIMITED")
        self.assertEqual(v("buyer"), "NORTHSTAR IMPORTS LTD")
        self.assertEqual(v("lc_number"), "LC2026100045")
        self.assertEqual(v("lc_date"), date(2026, 10, 1))
        self.assertEqual(v("issuing_bank"), "EXAMPLE BANK PLC, LONDON")
        self.assertEqual(v("port_of_loading"), "CHITTAGONG, BANGLADESH")
        self.assertEqual(v("port_of_discharge"), "FELIXSTOWE, UNITED KINGDOM")
        self.assertEqual(v("shipment_date"), date(2026, 11, 25))
        self.assertEqual(v("terms"), "CIF FELIXSTOWE")
        self.assertEqual(v("quantity"), Decimal("5000"))
        self.assertEqual(v("unit"), "PIECES")
        self.assertEqual(v("unit_price"), Decimal("25.00"))
        self.assertEqual(v("total_amount"), Decimal("125000.00"))
        self.assertEqual(v("currency"), "USD")
        self.assertIn("100 PERCENT COTTON", v("goods_description"))

    def test_no_warnings(self):
        self.assertEqual(self.r["warnings"], [])

    def test_evidence_is_kept(self):
        self.assertEqual(self.r["fields"]["lc_number"]["evidence"], "Letter of Credit No: LC2026100045")

    def test_all_field_names_exist(self):
        self.assertEqual(set(self.r["fields"]), set(FIELD_NAMES))


class InvoiceA(unittest.TestCase):
    def test_seeded_values_are_read_as_written(self):
        r = load("invoice_a_errors.txt")
        self.assertEqual(val(r, "buyer"), "NORTHSTAR IMPORT LTD")
        self.assertEqual(val(r, "lc_number"), "LC2026100054")
        self.assertEqual(val(r, "currency"), "EUR")
        self.assertEqual(r["warnings"], [])  # EUR everywhere, so the invoice agrees with itself


class InvoiceB(unittest.TestCase):
    def test_missing_fields_are_none(self):
        r = load("invoice_b_errors.txt")
        self.assertIsNone(r["fields"]["lc_number"])
        self.assertIsNone(r["fields"]["lc_date"])

    def test_other_values(self):
        r = load("invoice_b_errors.txt")
        self.assertEqual(val(r, "shipment_date"), date(2026, 12, 20))
        self.assertEqual(val(r, "quantity"), Decimal("5150"))
        self.assertEqual(val(r, "total_amount"), Decimal("128750.00"))
        self.assertIn("POLYESTER", val(r, "goods_description"))
        self.assertEqual(r["warnings"], [])


class Edges(unittest.TestCase):
    def test_empty_text(self):
        r = parse_invoice("")
        self.assertTrue(all(v is None for v in r["fields"].values()))

    def test_bad_arithmetic_gives_warning(self):
        text = (
            "Total Amount: USD 100.00\n"
            "SHIRTS   10 PIECES    USD 5.00     USD 60.00\n"
        )
        r = parse_invoice(text)
        self.assertEqual(len(r["warnings"]), 2)

    def test_bad_date_gives_warning(self):
        r = parse_invoice("Invoice Date: soon")
        self.assertIsNone(r["fields"]["invoice_date"])
        self.assertEqual(len(r["warnings"]), 1)

    def test_date_formats(self):
        self.assertEqual(parse_date("20 November 2026"), date(2026, 11, 20))
        self.assertEqual(parse_date("20-Nov-2026"), date(2026, 11, 20))
        self.assertEqual(parse_date("2026-11-20"), date(2026, 11, 20))
        self.assertIsNone(parse_date("someday"))


if __name__ == "__main__":
    unittest.main()
