import copy
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from tests.domain_mocks import install_domain_mock

from app.main import app
from app.behavior import ATTACK_TYPES
from app.scoring import combine_page, score_metadata
from app.services.suspicious_patterns import check_suspicious_patterns
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


def complete_response(url="https://example.com"):
    attacks = [{"type": kind, "severity": "none", "evidence_ids": []} for kind in ATTACK_TYPES]
    return combine_page(response(url), {"status": "ok", "ai_status": "generated",
                                        "attack_types": attacks, "readable": True})


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
        r = complete_response()
        self.assertEqual(combined_verdict(r)["level"], "낮음")
        self.assertEqual(combined_verdict({**r, "assessment_status": "partial"})["level"], "확인 불가")

    def test_naver_qr_redirect_reproduces_screenshot_with_caution_not_zero(self):
        r = complete_response("https://m.site.naver.com/1vSl3")
        r["page"]["final_url"] = "https://ece.cbnu.ac.kr/ECE"
        r["final_url_analysis"] = analyze_url_signals(r["page"]["final_url"], [], None)
        v = combined_verdict(r)
        self.assertEqual((v["score"], v["level"], v["assessment_status"]), (20, "주의", "complete"))
        self.assertEqual(codes(v), ["SHORT_URL"])

    def test_short_url_hosts_are_exact_and_normalized(self):
        for host in ("m.site.naver.com", "M.SITE.NAVER.COM.", "naver.me"):
            with self.subTest(host=host):
                self.assertIn("SHORT_URL", check_suspicious_patterns("https://" + host + "/demo")["codes"])
        for host in ("naver.com", "m.site.naver.com.evil.example", "naver.me.evil.example", "notnaver.me"):
            with self.subTest(host=host):
                self.assertNotIn("SHORT_URL", check_suspicious_patterns("https://" + host + "/demo")["codes"])

    def test_unknown_zero_stays_partial_without_an_uncertainty_penalty(self):
        r = response("https://example.com", complete=False)
        v = combined_verdict(r)
        self.assertEqual((v["score"], v["level"], v["assessment_status"]), (0, "확인 불가", "partial"))

    def test_empty_missing_duplicate_or_unknown_ai_categories_cannot_be_low(self):
        valid = complete_response()
        for attacks in ([], valid["attack_types"][:3], [valid["attack_types"][0]] * 4,
                        [{**a, "severity": "unknown" if i == 0 else "none"}
                         for i, a in enumerate(valid["attack_types"])]):
            with self.subTest(attacks=attacks):
                r = {**valid, "attack_types": attacks}
                self.assertEqual(combined_verdict(r)["level"], "확인 불가")
                page = {**valid["page"], "attack_types": attacks}
                scored = combine_page(response("https://example.com"), page)
                self.assertEqual(scored["assessment_status"], "partial")

    def test_registry_failure_and_unmeasured_patterns_cannot_be_low(self):
        for final in (False, True):
            for failure in ("registry", "pattern"):
                r = complete_response()
                analysis = copy.deepcopy(r["url_analysis"])
                if failure == "registry":
                    analysis.update(status="partial", errors=["BRAND_DB_UNAVAILABLE"])
                else:
                    analysis["risk_signals"]["suspicious_url_pattern"] = None
                r["final_url_analysis" if final else "url_analysis"] = analysis
                v = combined_verdict(r)
                self.assertEqual((v["score"], v["level"], v["assessment_status"]), (0, "확인 불가", "partial"))

    def test_optional_brand_is_skipped_but_requested_unknown_brand_is_incomplete(self):
        r = complete_response()
        self.assertEqual(combined_verdict(r)["level"], "낮음")
        self.assertEqual(combined_verdict(r, brand_requested=True)["level"], "확인 불가")

    def test_final_url_without_local_check_is_incomplete(self):
        r = complete_response()
        r["page"]["final_url"] = "https://other.example/landing"
        self.assertEqual(combined_verdict(r)["assessment_status"], "partial")

    def test_unreadable_page_is_incomplete_even_if_ai_claims_none(self):
        r = complete_response()
        scored = combine_page(response("https://example.com"), {**r["page"], "readable": False})
        self.assertEqual(scored["level"], "확인 불가")

    def test_observed_risk_survives_other_unknown_categories(self):
        r = complete_response()
        attacks = copy.deepcopy(r["attack_types"])
        attacks[0].update(severity="strong", evidence_ids=["page_text_1"])
        attacks[1]["severity"] = "unknown"
        scored = combine_page(response("https://example.com"), {**r["page"], "attack_types": attacks})
        v = combined_verdict(scored)
        self.assertEqual((v["score"], v["level"], v["assessment_status"]), (60, "위험", "partial"))

    def test_score_is_capped(self):
        r = response("https://bit.ly/setup.apk", ["스타벅스"], tls="invalid", age=1)
        r["components"] = {**r["components"], "ai_behavior": 60}
        self.assertEqual(combined_verdict(r)["score"], 100)


class VerdictAPITests(unittest.TestCase):
    def setUp(self):
        self.domain_search = install_domain_mock(self)

    def test_api_returns_naver_shortener_caution_with_completion_status(self):
        url = "https://m.site.naver.com/1vSl3"
        inspected = complete_response(url)
        inspected["page"].update(final_url="https://ece.cbnu.ac.kr/ECE", ai_model="mock-model",
                                  ai_assessment="no_obvious_signals")
        with patch("app.main.analyze_url", AsyncMock(return_value=copy.deepcopy(metadata(url)))), \
             patch("app.main.inspect_page", AsyncMock(return_value=inspected)), \
             patch("httpx.AsyncClient.post", AsyncMock()) as post, TestClient(app) as client:
            result = client.post("/api/analyze", json={"qr_text": url, "brand_texts": [],
                                                       "inspect_page": True, "include_explanation": False})
        self.assertEqual(result.status_code, 200)
        data = result.json()
        self.assertEqual(data["score"], 0)  # Legacy behavior-only score.
        self.assertEqual(data["verdict"]["score"], 20)
        self.assertEqual(data["verdict"]["level"], "주의")
        self.assertEqual(data["verdict"]["assessment_status"], "complete")
        self.assertIn("SHORT_URL", data["url_analysis"]["risk_signals"]["pattern_codes"])
        self.assertFalse(data["auto_open"])
        post.assert_not_called()

    def test_api_returns_verdict_without_changing_behavior_v1(self):
        url = "https://example.com/setup.apk"
        with patch("app.main.analyze_url", AsyncMock(return_value=copy.deepcopy(metadata(url)))), \
             patch("httpx.AsyncClient.post", AsyncMock()) as post, TestClient(app) as client:
            data = client.post("/api/analyze", json={"qr_text": url, "brand_texts": []}).json()
        self.assertEqual(data["score"], 0)
        self.assertEqual(data["score_version"], "metadata-v2")
        self.assertEqual(data["verdict"]["level"], "위험")
        self.assertEqual(data["verdict"]["score"], 50)
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
