import io
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.middleware.ocr_upload import OCRUploadLimitMiddleware
from app.scoring import score_metadata
from app.services.brand_extraction import BrandRegistryUnavailable
from app.services.ocr import OCRUnavailable, _pipeline_lock

BOX = [[2, 2], [95, 2], [95, 35], [2, 35]]


def picture(fmt="PNG", size=(100, 60), **kwargs):
    with Image.new("RGB", size, "white") as image:
        stream = io.BytesIO()
        image.save(stream, format=fmt, **kwargs)
    return stream.getvalue()


class OCRAPITests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.reader = MagicMock()
        self.reader.readtext.return_value = [(BOX, "STARBUCKS COFFEE", 0.95)]
        patcher = patch("app.services.ocr.get_reader", return_value=self.reader)
        patcher.start()
        self.addCleanup(patcher.stop)
        settings = patch("app.services.ocr.ocr_settings", return_value={"model_dir": None, "min_confidence": 0.65})
        settings.start()
        self.addCleanup(settings.stop)

    def upload(self, data=None, mime="image/png"):
        return self.client.post("/api/ocr/brands", files={"image": ("photo.png", picture() if data is None else data, mime)})

    def test_upload_returns_candidates_and_confirmation_without_ai_or_url_requests(self):
        with patch("httpx.AsyncClient.post", AsyncMock()) as paid, patch("app.security.resolve", AsyncMock()) as dns:
            response = self.upload()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["ocr_status"], "ok")
        self.assertEqual(data["brand_texts"], ["스타벅스"])
        self.assertTrue(data["requires_confirmation"])
        self.assertEqual(data["processed_width"], 100)
        self.assertEqual(data["brand_candidates"][0]["ocr_confidence"], 0.95)
        paid.assert_not_called()
        dns.assert_not_called()

    def test_low_confidence_and_multiple_brands_require_selection(self):
        self.reader.readtext.return_value = [(BOX, "STARBUCKS", 0.4)]
        data = self.upload().json()
        self.assertEqual(data["ocr_status"], "low_confidence")
        self.assertEqual(data["brand_texts"], [])
        self.reader.readtext.return_value = [(BOX, "NAVER", 0.99), (BOX, "스타벅스", 0.9)]
        data = self.upload().json()
        self.assertEqual(data["ocr_status"], "ambiguous")
        self.assertEqual(len(data["brand_candidates"]), 2)
        self.assertEqual(data["brand_texts"], [])

    def test_empty_unregistered_and_malformed_ocr_results(self):
        for raw, status in [([], "no_text"), ([(BOX, "WELCOME", 0.99)], "no_brand"),
                            ([(BOX, "NAVER", float("nan"))], "no_text")]:
            with self.subTest(status=status):
                self.reader.readtext.return_value = raw
                data = self.upload().json()
                self.assertEqual(data["ocr_status"], status)
                self.assertEqual(data["brand_texts"], [])

    def test_invalid_file_missing_upload_and_size_limits(self):
        self.assertEqual(self.client.post("/api/ocr/brands").status_code, 422)
        self.assertEqual(self.upload(b"not-an-image").status_code, 400)
        self.assertEqual(self.upload(b"<svg/>", "image/svg+xml").status_code, 415)
        self.assertEqual(self.upload(b"x" * (5 * 1024 * 1024 + 1)).status_code, 413)
        self.reader.readtext.assert_not_called()

    def test_engine_registry_and_config_failures_are_not_safe_results(self):
        with patch("app.services.ocr.get_reader", side_effect=OCRUnavailable("private-path")):
            response = self.upload()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private-path", response.text)
        with patch("app.services.ocr.extract_brand_candidates", side_effect=BrandRegistryUnavailable()):
            self.assertEqual(self.upload().status_code, 503)
        with patch("app.services.ocr.ocr_settings", side_effect=ValueError("bad settings")):
            self.assertEqual(self.upload().status_code, 503)

    def test_busy_request_does_not_start_another_inference(self):
        _pipeline_lock.acquire()
        try:
            response = self.upload()
        finally:
            _pipeline_lock.release()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers["retry-after"], "3")
        self.reader.readtext.assert_not_called()

    def test_confirmed_brand_can_be_passed_to_existing_analysis(self):
        brand_texts = self.upload().json()["brand_texts"]
        url = "https://www.starbucks.co.kr"
        checks = {"dns": {"status": "ok"}, "rdap": {"status": "ok", "age_days": 400},
                  "tls": {"status": "ok"}, "geoip": {"status": "ok"}}
        base = {"url": url, "hostname": "www.starbucks.co.kr", "evidence": checks, **score_metadata(url, checks)}
        with patch("app.main.analyze_url", AsyncMock(return_value=base)):
            response = self.client.post("/api/analyze", json={"qr_text": url, "brand_texts": brand_texts, "include_ai": False})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["url_analysis"]["risk_signals"]["brand_domain_status"], "matched")


class UploadLimitTests(unittest.IsolatedAsyncioTestCase):
    async def test_chunked_body_is_limited_before_parser_without_content_length(self):
        inner = AsyncMock()
        middleware = OCRUploadLimitMiddleware(inner)
        receive = AsyncMock(side_effect=[{"type": "http.request", "body": b"x"*10, "more_body": True},
                                         {"type": "http.request", "body": b"x"*10, "more_body": False}])
        send = AsyncMock()
        scope = {"type": "http", "method": "POST", "path": "/api/ocr/brands", "headers": []}
        with patch("app.middleware.ocr_upload.MAX_OCR_BODY_BYTES", 16):
            await middleware(scope, receive, send)
        inner.assert_not_called()
        self.assertEqual(send.call_args_list[0].args[0]["status"], 413)

if __name__ == "__main__":
    unittest.main()
