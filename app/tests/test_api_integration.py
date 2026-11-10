
import unittest

from fastapi.testclient import TestClient
from app.url_analysis_api import app


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



if __name__ == "__main__":
    unittest.main()
