import json
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase

from lccheck.explain import verify_quoted_evidence
from lccheck.models import OfficerDecision

DATA = Path(__file__).resolve().parents[2] / "testdata" / "lc"


def read(name):
    return (DATA / name).read_text(encoding="utf-8")


class CheckPage(TestCase):
    def post(self, **body):
        return self.client.post("/lc/api/check", data=json.dumps(body), content_type="application/json")

    def test_page_loads(self):
        r = self.client.get("/lc/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "LC Check")
        self.assertContains(r, "Officer Decision")
        self.assertContains(r, "AI Explanation")

    def test_correct_invoice_has_only_matches(self):
        r = self.post(lc=read("mt700_lc2026100045.txt"), amendments=[], invoice=read("invoice_ok.txt"))
        data = r.json()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(data["summary"]["MATCH"], len(data["results"]))
        self.assertEqual(data["lc_info"]["lc_number"], "LC2026100045")
        self.assertEqual(data["invoice_info"]["invoice_number"], "BKL/INV/2026/0412")

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

    # ---------- LC-5: Officer Decisions and AI Explanations ----------

    def test_officer_decision_save_and_reload(self):
        """Saving an officer decision persists to SQLite and shows on subsequent check."""
        resp = self.client.post(
            "/lc/api/decision",
            data=json.dumps({
                "lc_number": "LC2026100045",
                "invoice_number": "BKL/INV/2026/0431",
                "field": "goods_description",
                "decision": "REJECT",
                "comment": "Polyester is not acceptable; cotton required.",
                "ai_explanation": "Invoice shows polyester instead of 100% cotton.",
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["decision"], "REJECT")

        # Verify record in database
        rec = OfficerDecision.objects.get(lc_number="LC2026100045", field="goods_description")
        self.assertEqual(rec.decision, "REJECT")
        self.assertIn("Polyester", rec.comment)

        # Check invoice B again: the decision should be returned in the results payload
        check_resp = self.post(
            lc=read("mt700_lc2026100045.txt"),
            amendments=[],
            invoice=read("invoice_b_errors.txt"),
        )
        check_data = check_resp.json()
        goods_row = next(r for r in check_data["results"] if r["field"] == "goods_description")
        self.assertEqual(goods_row["decision"], "REJECT")
        self.assertEqual(goods_row["comment"], "Polyester is not acceptable; cotton required.")
        self.assertEqual(goods_row["ai_explanation"], "Invoice shows polyester instead of 100% cotton.")
        self.assertEqual(check_data["decision_summary"]["REJECT"], 1)

    def test_officer_decision_validation(self):
        # Invalid decision value
        r = self.client.post(
            "/lc/api/decision",
            data=json.dumps({"lc_number": "LC123", "field": "amount", "decision": "INVALID_CHOICE"}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("Invalid decision", r.json()["error"])

        # Missing required field
        r = self.client.post(
            "/lc/api/decision",
            data=json.dumps({"lc_number": "", "field": "amount", "decision": "ACCEPT"}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    def test_quote_verification_helper(self):
        context = ["5000 PIECES OF MEN'S COTTON KNITTED T-SHIRTS", "100 PERCENT COTTON"]
        
        # Valid quote that exists in context
        valid, unverified = verify_quoted_evidence('The requirement is "100 percent cotton".', context)
        self.assertTrue(valid)
        self.assertEqual(unverified, [])

        # Hallucinated quote that does not exist in context
        valid2, unverified2 = verify_quoted_evidence('The invoice says "Organic Silk Blends".', context)
        self.assertFalse(valid2)
        self.assertEqual(unverified2, ["Organic Silk Blends"])

    @patch("lccheck.explain.ask_model")
    def test_api_explain_endpoint(self, mock_ask):
        mock_ask.return_value = {
            "reply": 'The invoice specifies "polyester" instead of "100 percent cotton".',
            "seconds": 1.2,
        }

        resp = self.client.post(
            "/lc/api/explain",
            data=json.dumps({
                "field_info": {
                    "field": "goods_description",
                    "label": "Goods",
                    "status": "MISMATCH",
                    "lc_tag": "45A",
                    "lc_value": "100 PERCENT COTTON",
                    "doc_value": "100 PERCENT POLYESTER",
                    "evidence": "MEN'S POLYESTER KNITTED T-SHIRTS",
                    "note": "Words on invoice not in LC: POLYESTER",
                    "lc_number": "LC2026100045",
                    "invoice_number": "BKL/INV/2026/0431",
                }
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("polyester", data["explanation"])
        self.assertTrue(data["quotes_valid"])

        # Also verify it persisted to OfficerDecision
        rec = OfficerDecision.objects.get(lc_number="LC2026100045", field="goods_description")
        self.assertIn("polyester", rec.ai_explanation)
