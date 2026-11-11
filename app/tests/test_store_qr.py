
import unittest

from app.services.store_qr_verifier import verify_store_qr


class TestStoreQR(unittest.TestCase):

    # 1. 등록된 정상 QR 검사
    def test_matched_qr(self):
        result = verify_store_qr(
            "https://menu.example.com/store/demo-cafe-01",
            "demo-cafe-01"
        )

        self.assertEqual(result["status"], "matched")

    # 2. 등록된 주소와 다른 QR 검사
    def test_mismatched_qr(self):
        result = verify_store_qr(
            "https://fake-menu.example.com/store/demo-cafe-01",
            "demo-cafe-01"
        )

        self.assertEqual(result["status"], "mismatched")

    # 3. 등록되지 않은 매장 검사
    def test_unknown_store(self):
        result = verify_store_qr(
            "https://example.com",
            "unknown-cafe"
        )

        self.assertEqual(result["status"], "unknown")

    # 4. 잘못된 URL 검사
    def test_invalid_qr(self):
        result = verify_store_qr(
            "not-a-url",
            "demo-cafe-01"
        )

        self.assertEqual(result["status"], "invalid_url")


    # 5. 테스트용 매장은 주소가 일치해도 인증된 매장이 아님
    def test_unverified_store(self):
        result = verify_store_qr(
            "https://menu.example.com/store/demo-cafe-01",
            "demo-cafe-01"
        )

        # QR 주소는 등록된 주소와 일치
        self.assertEqual(result["status"], "matched")

        # 매장 정보는 테스트용
        self.assertEqual(
            result["verification_status"], "demo"
        )

        # 실제 매장 인증은 되지 않음
        self.assertFalse(result["is_store_verified"])


    # 6. 허용된 테이블 번호 QR
    def test_allowed_table_qr(self):
        result = verify_store_qr(
            "https://menu.example.com/store/demo-cafe-01?table=3",
            "demo-cafe-01"
        )

        self.assertEqual(result["status"], "matched")
        self.assertFalse(result["is_store_verified"])

    # 7. 허용하지 않은 쿼리 매개변수
    def test_disallowed_query(self):
        result = verify_store_qr(
            "https://menu.example.com/store/demo-cafe-01?next=https://fake.example",
            "demo-cafe-01"
        )

        self.assertEqual(result["status"], "mismatched")

    # 8. 잘못된 테이블 번호
    def test_invalid_table_number(self):
        result = verify_store_qr(
            "https://menu.example.com/store/demo-cafe-01?table=0",
            "demo-cafe-01"
        )

        self.assertEqual(result["status"], "mismatched")

    # 9. 테이블 번호를 중복해서 입력한 경우
    def test_duplicate_table_number(self):
        result = verify_store_qr(
            "https://menu.example.com/store/demo-cafe-01?table=1&table=2",
            "demo-cafe-01"
        )

        self.assertEqual(result["status"], "mismatched")


    # 10. 미검증 매장의 QR 주소가 일치하는 경우
    def test_unverified_matched_reason(self):
        result = verify_store_qr(
            "https://menu.example.com/store/demo-cafe-01?table=3",
            "demo-cafe-01"
        )

        self.assertEqual(result["status"], "matched")
        self.assertFalse(result["is_store_verified"])
        self.assertIn("일치하지만", result["reason"])
        self.assertIn("승인 여부", result["reason"])

    # 11. 미검증 매장의 QR 주소가 다른 경우
    def test_unverified_mismatched_reason(self):
        result = verify_store_qr(
            "https://menu.example.com/store/demo-cafe-01?table=0",
            "demo-cafe-01"
        )

        self.assertEqual(result["status"], "mismatched")
        self.assertFalse(result["is_store_verified"])
        self.assertIn("다릅니다", result["reason"])
        self.assertIn("진위는 확인할 수 없습니다", result["reason"])





if __name__ == "__main__":
    unittest.main()
