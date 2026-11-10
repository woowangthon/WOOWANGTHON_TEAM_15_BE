
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


if __name__ == "__main__":
    unittest.main()
