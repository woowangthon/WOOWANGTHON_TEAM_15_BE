import copy
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from app.main import app
from app.ai import summary_for_ai
from tests.domain_mocks import install_domain_mock
from tests.test_verdict import complete_response, metadata
from app.behavior import unknown_attacks


class MetadataPolicyTests(unittest.TestCase):
    def setUp(self):
        install_domain_mock(self)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def analyze(self, inspected, brands=()):
        url = inspected["url"]
        inspected["page"].setdefault("ai_model", None)
        with patch("app.main.analyze_url", AsyncMock(return_value=metadata(url))), \
             patch("app.main.inspect_page", AsyncMock(return_value=copy.deepcopy(inspected))):
            response = self.client.post("/api/analyze", json={"qr_text":url, "brand_texts":list(brands), "inspect_page":True})
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_unavailable_page_ai_does_not_block_complete_low_domain_assessment(self):
        url = "https://naver.com"
        data = complete_response(url)
        data["page"].update(status="unknown", ai_status="unavailable", ai_assessment="inconclusive", final_url=url)
        data["attack_types"] = unknown_attacks()
        data["components"]["ai_behavior"] = None
        data["assessment_status"] = "partial"
        result = self.analyze(data)
        self.assertEqual(result["score_scope"], "tls_domain_age")
        self.assertEqual(result["score_version"], "metadata-v2")
        self.assertEqual(result["verdict"]["version"], "combined-v2")
        self.assertEqual(result["verdict"]["assessment_status"], "complete")
        self.assertEqual((result["verdict"]["score"], result["verdict"]["level"]), (0, "낮음"))

    def test_strong_page_ai_does_not_add_points_or_enter_explanation_input(self):
        url = "https://naver.com"
        data = complete_response(url)
        data["page"].update(ai_assessment="suspicious", final_url=url)
        data["attack_types"][0].update(severity="strong", evidence_ids=["page_text_1"])
        data["components"]["ai_behavior"] = 60
        data["score"] = 60
        data["reasons"] = [{"code":"AI_CREDENTIAL_THEFT_STRONG", "points":60, "message":"test", "evidence_ids":[]}]
        result = self.analyze(data)
        self.assertEqual(result["components"]["ai_behavior"], None)
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["verdict"]["score"], 0)
        self.assertFalse(any(r["code"].startswith("AI_") for r in result["verdict"]["reasons"]))
        self.assertNotIn("page_attacks", summary_for_ai(result))

    def test_remaining_metadata_uncertainty_stays_unknown_and_brand_risk_stays_danger(self):
        url = "https://naver-event.xyz"
        data = complete_response(url)
        data["page"].update(ai_assessment="inconclusive", final_url=url)
        result = self.analyze(data, ["네이버"])
        self.assertEqual((result["verdict"]["score"], result["verdict"]["level"]), (50, "위험"))
        url = "https://naver.com"
        data = complete_response(url)
        data["page"].update(ai_assessment="inconclusive", final_url=url)
        data["evidence"]["geoip"]["status"] = "unknown"
        data["evidence_complete"] = False
        result = self.analyze(data)
        self.assertEqual(result["verdict"]["level"], "확인 불가")
