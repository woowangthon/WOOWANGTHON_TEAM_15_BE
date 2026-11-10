
import unittest

from fastapi.testclient import TestClient
from app.main import app


class TestAPIIntegration(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_store_search_and_qr_analysis(self):
        # 1. 매장 검색 API 호출
        search_response = self.client.get(
            "/api/stores/search",
            params={"keyword": "테스트카페"}
        )

        self.assertEqual(search_response.status_code, 200)

        search_data = search_response.json()

        self.assertEqual(search_data["count"], 1)

        # 2. 검색된 매장 ID 가져오기
        store_id = search_data["stores"][0]["store_id"]

        # 3. QR 분석 API 호출
        analyze_response = self.client.post(
            "/api/analyze",
            json={
                "qr_text": (
                    "https://menu.example.com/"
                    "store/demo-cafe-01?table=3"
                ),
                "brand_texts": [],
                "store_id": store_id
            }
        )

        self.assertEqual(analyze_response.status_code, 200)

        result = analyze_response.json()

        # 4. QR 분석 결과 확인
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["store_qr"]["status"], "matched")
        self.assertFalse(result["store_qr"]["is_store_verified"])

    
    # 등록되지 않은 매장 QR 분석 테스트
    def test_unknown_store_analysis(self):

        # 1. 등록되지 않은 매장 ID로 분석 요청
        response = self.client.post(
            "/api/analyze",
            json={
                "qr_text": "https://example.com/menu",
                "brand_texts": [],
                "store_id": "unknown-cafe"
            }
        )

        # 2. API 요청이 정상 처리됐는지 확인
        self.assertEqual(response.status_code, 200)

        # 3. JSON 결과 가져오기
        result = response.json()

        # 4. 매장 정보가 없으면 unknown이어야 함
        self.assertEqual(
            result["store_qr"]["status"],
            "unknown"
        )

        # 5. 인증된 매장으로 판단하면 안 됨
        self.assertFalse(
            result["store_qr"]["is_store_verified"]
        )

    
    # 위험 신호 데이터가 API에서 정상 반환되는지 확인
    def test_risk_signals_response(self):
        # 1. QR 분석 API 요청
        response = self.client.post(
            "/api/analyze",
            json={
                "qr_text": (
                    "https://menu.example.com/"
                    "store/demo-cafe-01?table=3"
                ),
                "brand_texts": [],
                "store_id": "demo-cafe-01"
            }
        )

        # 2. HTTP 요청 성공 확인
        self.assertEqual(response.status_code, 200)

        # 3. 위험 신호 데이터 가져오기
        result = response.json()
        signals = result["risk_signals"]

        # 4. 검사 결과 확인
        self.assertTrue(signals["url_valid"])
        self.assertFalse(signals["suspicious_url_pattern"])
        self.assertEqual(signals["brand_domain_status"], "unknown")
        self.assertEqual(signals["store_qr_status"], "matched")
        self.assertFalse(signals["store_data_verified"])
        self.assertEqual(
            signals["domain_impersonation_status"],
            "host_matched"
        )
        self.assertFalse(signals["redirect_pattern_detected"])

    
    # 4. 미등록 매장의 위험 신호 확인
    def test_unknown_store_risk_signals(self):
        response = self.client.post(
            "/api/analyze",
            json={
                "qr_text": "https://example.com/menu",
                "brand_texts": [],
                "store_id": "unknown-cafe"
            }
        )

        self.assertEqual(response.status_code, 200)

        signals = response.json()["risk_signals"]

        # URL 자체는 정상적인 형식
        self.assertTrue(signals["url_valid"])

        # 등록되지 않은 매장
        self.assertEqual(
            signals["store_qr_status"],
            "unknown"
        )

        # 실제 매장 인증이 되지 않음
        self.assertFalse(
            signals["store_data_verified"]
        )

    # 5. 잘못된 URL의 위험 신호 확인
    def test_invalid_url_risk_signals(self):
        response = self.client.post(
            "/api/analyze",
            json={
                "qr_text": "not-a-url",
                "brand_texts": [],
                "store_id": "demo-cafe-01"
            }
        )

        self.assertEqual(response.status_code, 200)

        result = response.json()
        signals = result["risk_signals"]

        # URL 분석 실패
        self.assertEqual(
            result["status"],
            "invalid_url"
        )

        self.assertFalse(signals["url_valid"])

        # 매장 QR 비교도 불가능
        self.assertEqual(
            signals["store_qr_status"],
            "invalid_url"
        )

        # 검사 불가능과 위험 없음은 다름
        self.assertIsNone(
            signals["suspicious_url_pattern"]
        )


if __name__ == "__main__":
    unittest.main()
