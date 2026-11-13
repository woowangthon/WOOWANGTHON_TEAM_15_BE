import copy
import json
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.ai import summary_for_ai
from app.brand_ocr import parse_ocr
from app.main import app
from app.services.printed_domain import compare_printed_domains, registered_domain
from tests.test_verdict import metadata


class RegisteredDomainTests(unittest.TestCase):
    def test_normalizes_printed_text(self):
        for text, expected in [
            ("www.starbucks.co.kr", "starbucks.co.kr"),
            ("https://m.Starbucks.co.kr/menu?x=1", "starbucks.co.kr"),
            ("naver.com/event.", "naver.com"),
            ("(store.example.com)", "example.com"),
        ]:
            with self.subTest(text=text):
                self.assertEqual(registered_domain(text), expected)

    def test_rejects_non_domains(self):
        for text in ["스타벅스", "1588-3820", "1.1.1.1", "localhost", "two words.com", "", None]:
            with self.subTest(text=text):
                self.assertIsNone(registered_domain(text))


class CompareTests(unittest.TestCase):
    def test_statuses(self):
        self.assertEqual(compare_printed_domains(["https://m.starbucks.co.kr"], ["www.starbucks.co.kr"])["status"], "matched")
        self.assertEqual(compare_printed_domains(["https://starbucks-event.xyz"], ["starbucks.co.kr"])["status"], "mismatched")
        self.assertEqual(compare_printed_domains(["https://starbucks.co.kr"], [])["status"], "not_checked")
        self.assertEqual(compare_printed_domains(["https://starbucks.co.kr"], ["전화 1588"])["status"], "not_checked")

    def test_final_url_after_redirect_can_match(self):
        result = compare_printed_domains(["https://bit.ly/x", "https://www.starbucks.co.kr/"], ["starbucks.co.kr"])
        self.assertEqual(result["status"], "matched")


class OCRParseTests(unittest.TestCase):
    def test_domains_are_parsed_and_cleaned(self):
        brands, domains = parse_ocr(json.dumps({
            "brands": ["스타벅스"],
            "domains": ["www.starbucks.co.kr", "STARBUCKS.CO.KR/menu", "help@starbucks.co.kr", "아무글자", "x" * 120 + ".com"],
        }))
        self.assertEqual(brands, ["스타벅스"])
        self.assertEqual(domains, [{"text": "www.starbucks.co.kr", "domain": "starbucks.co.kr"}])

    def test_missing_domains_key_is_allowed(self):
        self.assertEqual(parse_ocr('{"brands": []}'), ([], []))


class AnalyzeAPITests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def post(self, url, printed):
        with patch("app.main.analyze_url", AsyncMock(return_value=copy.deepcopy(metadata(url)))), \
             patch("httpx.AsyncClient.post", AsyncMock()):
            return self.client.post("/api/analyze", json={"qr_text": url, "brand_texts": [], "printed_domains": printed}).json()

    def test_mismatch_adds_caution_points(self):
        data = self.post("https://starbucks-event.example.com", ["www.starbucks.co.kr"])
        self.assertEqual(data["printed_domain_check"], {"status": "mismatched", "printed": ["starbucks.co.kr"], "qr_domain": "example.com"})
        self.assertIn("PRINTED_DOMAIN_MISMATCH", [r["code"] for r in data["verdict"]["reasons"]])
        self.assertEqual(data["verdict"]["score"], 25)
        self.assertEqual(data["verdict"]["level"], "주의")
        self.assertEqual(data["score"], 0)  # behavior-v1 unchanged

    def test_match_and_not_checked_add_nothing(self):
        for printed, status in [(["example.com"], "matched"), ([], "not_checked")]:
            with self.subTest(status=status):
                data = self.post("https://www.example.com", printed)
                self.assertEqual(data["printed_domain_check"]["status"], status)
                self.assertNotIn("PRINTED_DOMAIN_MISMATCH", [r["code"] for r in data["verdict"]["reasons"]])

    def test_ai_summary_gets_status_only(self):
        data = self.post("https://starbucks-event.example.com", ["www.starbucks.co.kr"])
        summary = json.dumps(summary_for_ai(data), ensure_ascii=False)
        self.assertIn('"printed_domain_status": "mismatched"', summary)
        self.assertNotIn("starbucks.co.kr", summary)

    def test_too_many_printed_domains_is_rejected(self):
        response = self.client.post("/api/analyze", json={"qr_text": "https://example.com", "brand_texts": [],
                                                          "printed_domains": ["a.com"] * 11})
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
