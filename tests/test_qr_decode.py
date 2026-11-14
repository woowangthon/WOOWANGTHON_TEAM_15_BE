import base64
import io
import unittest
from unittest.mock import patch, AsyncMock

import zxingcpp
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient
from app.main import app


def qr(text, size=240):
    return Image.fromarray(zxingcpp.write_barcode(zxingcpp.BarcodeFormat.QRCode, text, size, size, quiet_zone=4)).convert("RGB")


def encoded(image, quality=80):
    with io.BytesIO() as out:
        image.save(out, format="JPEG", quality=quality)
        return base64.b64encode(out.getvalue()).decode()


def poster(text, rotate=False, off_center=False):
    image = Image.new("RGB", (1200, 1700), "white")
    ImageDraw.Draw(image).text((70, 80), "STARBUCKS WINTER EVENT - QR decoding test", fill="black")
    with qr(text) as code:
        image.paste(code, (80, 1100) if off_center else (480, 740))
    if rotate:
        result = image.transpose(Image.Transpose.ROTATE_90)
        image.close()
        return result
    return image


class QRDecodeTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def decode(self, image):
        return self.client.post("/api/qr/decode", json={"image_base64": encoded(image, quality=55)})

    def test_four_real_poster_qrs_decode_without_ai_or_visiting_target(self):
        urls = ["https://naver-event.xyz", "https://naver.com", "https://m.naver.com", "https://starbucks-event.example.com"]
        with patch("httpx.AsyncClient.request", AsyncMock(side_effect=AssertionError("No HTTP permitted"))), \
             patch("app.main.analyze_url", AsyncMock(side_effect=AssertionError("No target inspection"))), \
             patch("app.main.read_brands", AsyncMock(side_effect=AssertionError("No AI OCR"))):
            for i, url in enumerate(urls):
                with self.subTest(url=url), poster(url, rotate=i == 2, off_center=i == 3) as image:
                    result = self.decode(image)
                    self.assertEqual(result.status_code, 200)
                    self.assertEqual(result.json()["qr_text"], url)
                    self.assertEqual(result.json()["status"], "ok")
                    self.assertFalse(result.json()["auto_open"])

    def test_blank_is_not_found_and_different_qrs_require_user_choice(self):
        with Image.new("RGB", (900, 700), "white") as image:
            self.assertEqual(self.decode(image).json()["status"], "not_found")
            with qr("https://naver.com") as a, qr("https://example.com") as b:
                image.paste(a, (30, 100))
                image.paste(b, (530, 100))
            result = self.decode(image).json()
            self.assertEqual(result["status"], "multiple_qr")
            self.assertIsNone(result["qr_text"])

    def test_text_payload_is_returned_without_becoming_a_url(self):
        with poster("javascript:alert(1)") as image:
            result = self.decode(image).json()
            self.assertEqual(result["qr_text"], "javascript:alert(1)")
            self.assertFalse(result["auto_open"])

    def test_bad_image_large_dimensions_and_request_body_are_rejected(self):
        for value in ["https://suspect.example/picture.jpg", base64.b64encode(b"\\x89PNG\\r\\n\\x1a\\n" + b"broken" * 20).decode()]:
            self.assertEqual(self.client.post("/api/qr/decode", json={"image_base64": value}).status_code, 422)
        with Image.new("RGB", (4100, 4000), "white") as image:
            self.assertEqual(self.decode(image).status_code, 422)
        self.assertEqual(self.client.post("/api/qr/decode", content=b"{}", headers={"Content-Length":"4500000"}).status_code, 413)

    def test_busy_decoder_returns_retryable_error(self):
        from app.qr_decode import _slots
        self.assertTrue(_slots.acquire(False))
        self.assertTrue(_slots.acquire(False))
        try:
            with Image.new("RGB", (20, 20), "white") as image:
                self.assertEqual(self.decode(image).status_code, 503)
        finally:
            _slots.release()
            _slots.release()
