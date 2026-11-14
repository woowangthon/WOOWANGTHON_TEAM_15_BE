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


if __name__ == "__main__":
    unittest.main()
