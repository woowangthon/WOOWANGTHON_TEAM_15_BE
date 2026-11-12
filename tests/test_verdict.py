import copy
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.scoring import score_metadata
from app.services.url_analysis import analyze_url_signals
from app.verdict import combined_verdict


def metadata(url, age=400, tls="ok", complete=True):
    checks = {"dns": {"status": "ok", "addresses": ["8.8.8.8"]},
              "rdap": {"status": "ok", "age_days": age},
              "tls": {"status": tls}, "geoip": {"status": "ok" if complete else "unknown"}}
    return {"url": url, "hostname": "example.com", "evidence": checks, **score_metadata(url, checks)}


def response(url, brands=(), store=None, **meta):
    # Same shape main.py builds before calling combined_verdict.
    result = metadata(url, **meta)
    return {**result, "url_analysis": analyze_url_signals(url, list(brands), store), "final_url_analysis": None, "page": None}


def codes(verdict):
    return [r["code"] for r in verdict["reasons"]]


class CombinedVerdictTests(unittest.TestCase):
    def test_clean_url_keeps_behavior_v1_points(self):
        r = response("https://example.com", age=10)
        v = combined_verdict(r)
        self.assertEqual(v["score"], r["score"])
        self.assertEqual(v["version"], "combined-v1")
        self.assertIn("NEW_DOMAIN", codes(v))

    def test_signals_that_stop_the_user_reach_danger_alone(self):
        for url, brands, store, code in [
            ("https://example.com/setup.apk", (), None, "EXECUTABLE_DOWNLOAD"),
            ("https://example.com", ["스타벅스"], None, "BRAND_DOMAIN_MISMATCH"),
            ("https://menu.example.com.evil.example/store/demo-cafe-01", (), "demo-cafe-01", "STORE_DOMAIN_IMPERSONATION"),
        ]:
            with self.subTest(code=code):
                v = combined_verdict(response(url, brands, store))
                self.assertEqual(v["level"], "위험")
                self.assertGreaterEqual(v["score"], 50)
                self.assertIn(code, codes(v))

    def test_hidden_destination_signals_reach_caution(self):
        for url, code in [("https://bit.ly/demo", "SHORT_URL"), ("https://1.1.1.1", "IP_LITERAL")]:
            with self.subTest(code=code):
                v = combined_verdict(response(url))
                self.assertEqual(v["level"], "주의")
                self.assertIn(code, codes(v))

    def test_impersonation_is_not_also_counted_as_store_mismatch(self):
        v = combined_verdict(response("https://menu.example.com.evil.example/store/demo-cafe-01", store="demo-cafe-01"))
        self.assertIn("STORE_DOMAIN_IMPERSONATION", codes(v))
        self.assertNotIn("STORE_QR_MISMATCH", codes(v))

    def test_final_url_signals_count_once(self):
        r = response("https://bit.ly/setup.apk")
        r["final_url_analysis"] = analyze_url_signals("https://other.example/setup.apk", [], None)
        v = combined_verdict(r)
        self.assertEqual(codes(v).count("EXECUTABLE_DOWNLOAD"), 1)
        self.assertEqual(v["score"], r["score"] + 50 + 20)

    def test_blocked_target_is_danger_even_without_points(self):
        r = response("https://example.com")
        r["navigation_allowed"] = False
        v = combined_verdict(r)
        self.assertEqual(v["level"], "위험")
        self.assertIn("BLOCKED_NAVIGATION", codes(v))

    def test_low_needs_complete_assessment(self):
        r = response("https://example.com")
        self.assertEqual(combined_verdict({**r, "assessment_status": "complete"})["level"], "낮음")
        self.assertEqual(combined_verdict({**r, "assessment_status": "partial"})["level"], "확인 불가")

    def test_score_is_capped(self):
        r = response("https://bit.ly/setup.apk", ["스타벅스"], tls="invalid", age=1)
        r["components"] = {**r["components"], "ai_behavior": 60}
        self.assertEqual(combined_verdict(r)["score"], 100)


class VerdictAPITests(unittest.TestCase):
    def test_api_returns_verdict_without_changing_behavior_v1(self):
        url = "https://example.com/setup.apk"
        with patch("app.main.analyze_url", AsyncMock(return_value=copy.deepcopy(metadata(url)))), \
             patch("httpx.AsyncClient.post", AsyncMock()) as post, TestClient(app) as client:
            data = client.post("/api/analyze", json={"qr_text": url, "brand_texts": []}).json()
        self.assertEqual(data["score"], 0)
        self.assertEqual(data["score_version"], "behavior-v1")
        self.assertEqual(data["verdict"]["level"], "위험")
        self.assertEqual(data["verdict"]["score"], 50)
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
