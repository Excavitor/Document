import json
from pathlib import Path

from django.test import SimpleTestCase

DATA = Path(__file__).resolve().parents[2] / "testdata" / "lc"


def read(name):
    return (DATA / name).read_text(encoding="utf-8")


class CheckPage(SimpleTestCase):
    def post(self, **body):
        return self.client.post("/lc/api/check", data=json.dumps(body), content_type="application/json")

    def test_page_loads(self):
        r = self.client.get("/lc/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "LC Check")

    def test_correct_invoice_has_only_matches(self):
        r = self.post(lc=read("mt700_lc2026100045.txt"), amendments=[], invoice=read("invoice_ok.txt"))
        data = r.json()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(data["summary"]["MATCH"], len(data["results"]))
        self.assertEqual(data["lc_info"]["lc_number"], "LC2026100045")

    def test_invoice_b_with_amendment(self):
        r = self.post(lc=read("mt700_lc2026100045.txt"), amendments=[read("mt707_amendment_1.txt")],
                      invoice=read("invoice_b_errors.txt"))
        data = r.json()
        status = {x["field"]: x["status"] for x in data["results"]}
        self.assertEqual(status["lc_number"], "MISSING")
        self.assertEqual(status["goods_description"], "MISMATCH")
        self.assertEqual(status["shipment_date"], "MATCH")
        self.assertEqual(len(data["lc_info"]["amendments"]), 1)
        self.assertTrue(data["warnings"])

    def test_empty_inputs(self):
        self.assertEqual(self.post(lc="", invoice="x").status_code, 400)
        r = self.post(lc=read("mt700_lc2026100045.txt"), invoice="")
        self.assertEqual(r.status_code, 400)
        self.assertIn("invoice", r.json()["error"])

    def test_bad_lc(self):
        r = self.post(lc="hello", invoice=read("invoice_ok.txt"))
        self.assertEqual(r.status_code, 400)
        self.assertIn("LC problem", r.json()["error"])

    def test_amendment_for_another_lc(self):
        wrong = read("mt707_amendment_1.txt").replace("LC2026100045", "LC0000000000")
        r = self.post(lc=read("mt700_lc2026100045.txt"), amendments=[wrong], invoice=read("invoice_ok.txt"))
        self.assertEqual(r.status_code, 400)
        self.assertIn("Amendment 1", r.json()["error"])

    def test_unreadable_invoice(self):
        r = self.post(lc=read("mt700_lc2026100045.txt"), invoice="just some words")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Nothing could be read", r.json()["error"])

    def test_bad_json_and_bad_types(self):
        r = self.client.post("/lc/api/check", data="not json", content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.post(lc="x", invoice="y", amendments="oops").status_code, 400)

    def test_too_long(self):
        r = self.post(lc="x" * 100_001, invoice="y")
        self.assertEqual(r.status_code, 400)

    def test_get_not_allowed_on_api(self):
        self.assertEqual(self.client.get("/lc/api/check").status_code, 405)

    def test_samples(self):
        self.assertEqual(self.client.get("/lc/sample?name=invoice_ok").status_code, 200)
        self.assertEqual(self.client.get("/lc/sample?name=nope").status_code, 404)
        self.assertEqual(self.client.get("/lc/sample?name=../../manage.py").status_code, 404)
