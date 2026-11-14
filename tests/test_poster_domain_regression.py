"""The four reported poster cases; network evidence is controlled, not live-site safety tests."""
import json
import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app
from tests.test_domain_ai import payload, response, SETTINGS
from tests.test_verdict import metadata

class PosterDomainTests(unittest.TestCase):
    def test_four_domain_comparisons_and_scores(self):
        cases = [
            ("naver-event.xyz", [], [], "NAVER", ["naver.com", "navercorp.com"], "impersonation", "lookalike", "mismatched", "not_checked", 50),
            ("naver.com", ["스타벅스"], [], "스타벅스", ["starbucks.co.kr"], "impersonation", "unrelated", "mismatched", "not_checked", 50),
            ("m.naver.com", [], ["www.naver.com"], "NAVER", ["naver.com", "navercorp.com"], "official", "exact", "matched", "matched", 0),
            ("starbucks-event.example.com", ["스타벅스"], ["www.starbucks.co.kr"], "스타벅스", ["starbucks.co.kr"], "impersonation", "lookalike", "mismatched", "mismatched", 50),
        ]
        for host, brands, printed, org, domains, status, relation, expected, print_status, score in cases:
            with self.subTest(host=host):
                url = "https://" + host
                source = "https://" + domains[-1] + "/company"
                item = dict(hostname=host, status=status, organization=org, official_domains=domains,
                            source_urls=[source], relationship=relation, reason="공식 주소를 검색해 비교했습니다.")
                data = payload([item])
                data["output"][0]["action"]["sources"] = [{"url": source}]
                with patch("app.domain_ai.baze_settings", return_value=SETTINGS), \
                     patch.dict("os.environ", {"BAZE_DOMAIN_MODEL": ""}), \
                     patch("httpx.AsyncClient.post", AsyncMock(return_value=response(data))), \
                     patch("app.main.analyze_url", AsyncMock(return_value=metadata(url))), TestClient(app) as client:
                    result = client.post("/api/analyze", json={"qr_text": url, "brand_texts": brands,
                                                             "printed_domains": printed}).json()
                self.assertEqual(result["url_analysis"]["brand_domain"]["status"], expected)
                self.assertEqual(result["printed_domain_check"]["status"], print_status)
                self.assertEqual(result["verdict"]["score"], score)
                if score:
                    self.assertEqual(result["verdict"]["level"], "위험")
                else:
                    # All scored metadata/domain checks complete; page AI is excluded.
                    self.assertEqual(result["verdict"]["assessment_status"], "complete")
                self.assertFalse(result["auto_open"])
