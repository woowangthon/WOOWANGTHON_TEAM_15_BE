import unittest

from fastapi.testclient import TestClient

from app.main import app


class ErrorFormatTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_invalid_url_has_message_and_code(self):
        response = self.client.post("/api/analyze", json={"qr_text": "hello", "brand_texts": []})
        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["code"], "INVALID_URL")
        self.assertIsInstance(body["detail"], str)

    def test_validation_error_detail_is_a_string_with_field_list(self):
        response = self.client.post("/api/analyze", json={"brand_texts": []})
        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["code"], "VALIDATION_ERROR")
        self.assertIsInstance(body["detail"], str)
        self.assertIn("qr_text", [e["field"] for e in body["errors"]])

    def test_unknown_path_and_method(self):
        self.assertEqual(self.client.get("/api/nope").json()["code"], "NOT_FOUND")
        wrong = self.client.get("/api/analyze")
        self.assertEqual(wrong.status_code, 405)
        self.assertEqual(wrong.json()["code"], "METHOD_NOT_ALLOWED")
        self.assertIsInstance(wrong.json()["detail"], str)

    def test_ocr_upload_limit_uses_same_shape(self):
        response = self.client.post("/api/ocr/brands/local", headers={"content-length": "99999999999"}, content=b"")
        self.assertIn(response.status_code, (400, 413))
        self.assertIn("code", response.json())


    def test_qr_and_local_ocr_keep_distinct_limits_with_common_errors(self):
        # 4.5MB exceeds the QR JSON limit but fits the 5MiB local OCR limit.
        qr = self.client.post("/api/qr/decode", headers={"content-length": "4500000"}, content=b"{}")
        self.assertEqual(qr.status_code, 413)
        self.assertEqual(qr.json()["code"], "PAYLOAD_TOO_LARGE")
        local = self.client.post("/api/ocr/brands/local", headers={"content-length": "4500000"}, content=b"{}")
        self.assertEqual(local.status_code, 422)
        self.assertEqual(local.json()["code"], "VALIDATION_ERROR")
        self.assertIsInstance(local.json()["detail"], str)

    def test_chunked_qr_body_limit_also_uses_common_errors(self):
        chunks = (b"x" * 2_200_001 for _ in range(2))
        response = self.client.post("/api/qr/decode", content=chunks)
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["code"], "PAYLOAD_TOO_LARGE")
        self.assertIsInstance(response.json()["detail"], str)


if __name__ == "__main__":
    unittest.main()
