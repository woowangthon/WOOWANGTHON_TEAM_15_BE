import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from app.behavior import ATTACK_TYPES
from app.main import app
from app.page_analysis import _cache
from app.scoring import score_metadata
from app.services.url_analysis import analyze_url_signals


def metadata(url, age=400, blocked=False):
    checks = {"dns": {"status": "ok", "addresses": ["8.8.8.8"]},
              "rdap": {"status": "ok", "age_days": age},
              "tls": {"status": "ok"}, "geoip": {"status": "ok"}}
    if blocked:
        checks = {name: {"status": "unknown"} for name in checks}
        checks["dns"] = {"status": "blocked", "addresses": []}
    return {"url": url, "hostname": "example.com", "evidence": checks, **score_metadata(url, checks)}


class CombinedAnalysisTests(unittest.TestCase):
    def setUp(self):
        _cache.clear()
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_same_shared_results_with_store_id_and_brand_texts(self):
        url = "https://menu.example.com/store/demo-cafe-01?table=3"
        body = {"qr_text": url, "brand_texts": ["테스트브랜드"], "store_id": "demo-cafe-01"}
        with patch("app.main.analyze_url", AsyncMock(return_value=metadata(url))), patch("httpx.AsyncClient.post", AsyncMock()) as post:
            combined = self.client.post("/api/analyze", json=body)
            standalone = self.client.post("/api/url/analyze", json=body)
        self.assertEqual(combined.status_code, 200)
        self.assertEqual(standalone.status_code, 200)
        data = combined.json()
        self.assertEqual(data["url_analysis"], standalone.json())
        self.assertEqual(data["url_analysis"]["risk_signals"]["brand_domain_status"], "matched")
        self.assertEqual(data["url_analysis"]["risk_signals"]["store_qr_status"], "matched")
        self.assertFalse(data["url_analysis"]["risk_signals"]["store_data_verified"])
        self.assertEqual(data["score"], 0)
        self.assertEqual(data["assessment_status"], "partial")
        self.assertIsNone(data["final_url_analysis"])
        self.assertEqual(data["score_scope"], "ai_behavior_tls_domain_age")
        post.assert_not_called()

    def test_pattern_codes_are_stable_and_do_not_change_v1_points(self):
        url = "https://bit.ly/setup.apk?file=setup%252Eexe"
        with patch("app.main.analyze_url", AsyncMock(return_value=metadata(url))), patch("httpx.AsyncClient.post", AsyncMock()) as post:
            response = self.client.post("/api/analyze", json={
                "qr_text": url, "brand_texts": [], "include_ai": False,
                "score": 100, "risk_signals": {"suspicious_url_pattern": False}})
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["url_analysis"]["risk_signals"]["pattern_codes"],
                         ["SHORT_URL", "EXECUTABLE_LINK", "EXECUTABLE_QUERY"])
        self.assertTrue(data["url_analysis"]["risk_signals"]["suspicious_url_pattern"])
        self.assertEqual(data["score"], 0)
        self.assertEqual(data["score_version"], "behavior-v1")
        self.assertIn("behavior-v1", data["warning"])
        post.assert_not_called()

    def test_ai_pipeline_and_redirect_url_checks_are_combined_without_double_counting(self):
        source = "https://bit.ly/demo"
        final = "https://menu.example.com/store/demo-cafe-01?table=3"
        html = '<p>긴급 계정 정지. 비밀번호와 OTP를 즉시 입력하여 인증하세요.</p><form><input type="password"></form>'
        attacks = [{"type": kind, "severity": "strong" if kind == "credential_theft" else "none",
                    "evidence_ids": ["page_text_1", "form_1"] if kind == "credential_theft" else []}
                   for kind in ATTACK_TYPES]
        ai = httpx.Response(200, request=httpx.Request("POST", "https://gateway.example"),
                            json={"choices": [{"finish_reason": "stop", "message": {
                                "content": json.dumps({"attacks": attacks})}}]})
        fetched = {"status": "ok", "html": html, "http_status": 200, "final_url": final,
                   "redirect_chain": [{"url": source, "http_status": 302}, {"url": final, "http_status": 200}]}
        with patch("app.main.analyze_url", AsyncMock(return_value=metadata(source, 10))), \
             patch("app.page_analysis.analyze_url", AsyncMock(return_value=metadata(final))), \
             patch("app.page_analysis.fetch_page", AsyncMock(return_value=fetched)) as fetch, \
             patch("app.page_analysis.baze_settings", return_value={"api_key": "test-only", "model": "test-model", "base_url": "https://gateway.example"}), \
             patch("httpx.AsyncClient.post", AsyncMock(return_value=ai)) as post:
            response = self.client.post("/api/analyze", json={
                "qr_text": source, "brand_texts": [], "store_id": "demo-cafe-01",
                "inspect_page": True, "include_ai": True})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["score"], 75)
        self.assertEqual(data["components"], {"ai_behavior": 60, "tls": 0, "domain_age": 15})
        self.assertEqual(data["assessment_status"], "complete")
        self.assertEqual(data["ai_status"], "generated")
        self.assertEqual(data["url_analysis"]["risk_signals"]["pattern_codes"], ["SHORT_URL"])
        self.assertEqual(data["final_url_analysis"]["risk_signals"]["store_qr_status"], "matched")
        self.assertFalse(data["final_url_analysis"]["risk_signals"]["store_data_verified"])
        self.assertFalse(data["auto_open"])
        self.assertEqual(sum(r["points"] for r in data["reasons"]), 75)
        fetch.assert_awaited_once_with(source)
        post.assert_awaited_once()

    def test_registry_failure_preserves_known_checks_and_marks_unknown(self):
        url = "https://example.com/setup.apk"
        with patch("app.main.analyze_url", AsyncMock(return_value=metadata(url))), \
             patch("app.services.url_analysis.compare_brand_domain", side_effect=FileNotFoundError("private-path")), \
             patch("app.services.url_analysis.verify_store_qr", side_effect=ValueError("bad registry")), \
             patch("app.services.url_analysis.check_domain_impersonation", side_effect=TypeError("bad registry")):
            response = self.client.post("/api/analyze", json={
                "qr_text": url, "brand_texts": ["테스트브랜드"], "store_id": "demo-cafe-01"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        local = data["url_analysis"]
        self.assertEqual(local["status"], "partial")
        self.assertEqual(local["errors"], ["BRAND_DB_UNAVAILABLE", "STORE_DB_UNAVAILABLE", "IMPERSONATION_DB_UNAVAILABLE"])
        self.assertEqual(local["risk_signals"]["brand_domain_status"], "unknown")
        self.assertIsNone(local["risk_signals"]["store_data_verified"])
        self.assertEqual(local["risk_signals"]["pattern_codes"], ["EXECUTABLE_LINK"])
        self.assertNotIn("private-path", json.dumps(data))
        self.assertEqual(data["score"], 0)

    def test_blocked_dns_cannot_be_overridden_by_local_url_validity(self):
        url = "https://127.0.0.1"
        with patch("app.main.analyze_url", AsyncMock(return_value=metadata(url, blocked=True))), \
             patch("app.page_analysis.fetch_page", AsyncMock()) as fetch, \
             patch("httpx.AsyncClient.post", AsyncMock()) as post:
            response = self.client.post("/api/analyze", json={
                "qr_text": url, "brand_texts": [], "inspect_page": True})
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["url_analysis"]["risk_signals"]["url_valid"])
        self.assertEqual(data["url_analysis"]["risk_signals"]["pattern_codes"], ["IP_LITERAL"])
        self.assertIsNone(data["score"])
        self.assertFalse(data["navigation_allowed"])
        fetch.assert_not_called()
        post.assert_not_called()

    def test_invalid_url_fails_before_network_or_paid_analysis(self):
        for url in ["not-a-url", "https://user:pass@example.com", "https://example.com:22", "https://example.com/%zz"]:
            with self.subTest(url=url), patch("app.main.analyze_url", AsyncMock()) as metadata_probe, \
                 patch("app.main.inspect_page", AsyncMock()) as inspect:
                response = self.client.post("/api/analyze", json={
                    "qr_text": url, "brand_texts": [], "inspect_page": True})
                self.assertEqual(response.status_code, 422)
                metadata_probe.assert_not_called()
                inspect.assert_not_called()

    def test_long_url_contract_and_optional_store_id(self):
        url = "https://example.com/?q=" + "a" * 2500
        with patch("app.main.analyze_url", AsyncMock(return_value=metadata(url))):
            response = self.client.post("/api/analyze", json={"qr_text": url, "brand_texts": []})
        self.assertEqual(response.status_code, 200)
        signals = response.json()["url_analysis"]["risk_signals"]
        self.assertEqual(signals["store_qr_status"], "not_checked")
        self.assertIsNone(signals["store_data_verified"])

    def test_local_analysis_never_needs_target_or_ai_network(self):
        with patch("httpx.AsyncClient.post", AsyncMock()) as post, \
             patch("app.security.resolve", AsyncMock()) as resolve:
            report = analyze_url_signals("https://bit.ly/demo", [], "unknown-store")
        self.assertEqual(report["risk_signals"]["store_qr_status"], "unknown")
        self.assertEqual(report["risk_signals"]["pattern_codes"], ["SHORT_URL"])
        post.assert_not_called()
        resolve.assert_not_called()


if __name__ == "__main__":
    unittest.main()
