import copy
import json
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.ai import summary_for_ai
from app.main import app
from app.services.domain_keywords import check_domain_keywords
from tests.test_verdict import metadata


class CheckerTests(unittest.TestCase):
    def test_brand_inside_non_official_domain(self):
        for url in ["https://naver-event.xyz", "https://naver.com.login-check.xyz/a", "https://starbucks-event.example.com"]:
            with self.subTest(url=url):
                self.assertIsNotNone(check_domain_keywords([url])["brand_in_domain"])

    def test_official_domains_and_their_subdomains_are_not_flagged(self):
        for url in ["https://www.naver.com", "https://m.naver.com/login", "https://comic.naver.com", "https://www.starbucks.co.kr"]:
            with self.subTest(url=url):
                self.assertEqual(check_domain_keywords([url]), {"brand_in_domain": None, "domain_keywords": [], "path_keywords": []})

    def test_phishing_words_score_only_in_registered_domain(self):
        self.assertEqual(check_domain_keywords(["https://secure-login-verify.com"])["domain_keywords"], ["login", "verify", "secure"])
        info = check_domain_keywords(["https://login.example.org/account?next=refund"])
        self.assertEqual(info["domain_keywords"], [])
        self.assertEqual(info["path_keywords"], ["login", "account", "refund"])

    def test_demo_brand_and_ip_are_ignored(self):
        for url in ["https://example.com", "https://menu.example.com/store", "https://1.1.1.1"]:
            with self.subTest(url=url):
                self.assertIsNone(check_domain_keywords([url])["brand_in_domain"])

    def test_final_url_is_checked_too(self):
        self.assertIsNotNone(check_domain_keywords(["https://bit.ly/x", "https://naver-event.xyz/"])["brand_in_domain"])


class VerdictAPITests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def post(self, url, brands=()):
        with patch("app.main.analyze_url", AsyncMock(return_value=copy.deepcopy(metadata(url)))), patch("httpx.AsyncClient.post", AsyncMock()):
            return self.client.post("/api/analyze", json={"qr_text": url, "brand_texts": list(brands)}).json()

    def codes(self, data):
        return [r["code"] for r in data["verdict"]["reasons"]]

    def test_brand_in_domain_is_danger_alone(self):
        data = self.post("https://naver-event.xyz")
        self.assertEqual(data["domain_keyword_check"]["brand_in_domain"], {"word": "naver", "official": ["naver.com"]})
        self.assertIn("BRAND_IN_DOMAIN", self.codes(data))
        self.assertEqual(data["verdict"]["level"], "위험")
        self.assertEqual(data["score"], 0)  # behavior-v1 unchanged

    def test_phishing_word_domain_is_caution(self):
        data = self.post("https://secure-login-verify.com")
        self.assertEqual(self.codes(data), ["PHISHING_KEYWORD_DOMAIN"])
        self.assertEqual(data["verdict"]["level"], "주의")

    def test_not_double_counted_with_entered_brand(self):
        data = self.post("https://naver-event.xyz", ["네이버"])
        self.assertIn("BRAND_DOMAIN_MISMATCH", self.codes(data))
        self.assertNotIn("BRAND_IN_DOMAIN", self.codes(data))
        self.assertEqual(data["verdict"]["score"], 50)

    def test_path_words_add_no_points(self):
        data = self.post("https://login.example.org/account")
        self.assertEqual(data["domain_keyword_check"]["path_keywords"], ["login", "account"])
        self.assertEqual(data["verdict"]["reasons"], [])

    def test_ai_gets_flags_not_words(self):
        data = self.post("https://naver.com.login-check.xyz/")
        summary = json.dumps(summary_for_ai(data), ensure_ascii=False)
        self.assertIn('"brand_in_domain": true', summary)
        self.assertIn('"phishing_keyword_in_domain": true', summary)
        self.assertNotIn("login-check", summary)


if __name__ == "__main__":
    unittest.main()
