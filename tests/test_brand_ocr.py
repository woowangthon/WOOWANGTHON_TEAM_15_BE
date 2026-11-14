import base64
import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from app.brand_ocr import MAX_IMAGE_BYTES, UNAVAILABLE_MESSAGE, decode_image, parse_brands
from app.main import app

SETTINGS = {"api_key": "test-only-key", "base_url": "https://gateway.example/v1/gateway", "model": "gpt-6-luna"}
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
B64_PNG = base64.b64encode(PNG).decode()


def ai_reply(content, finish="stop"):
    return httpx.Response(200, request=httpx.Request("POST", SETTINGS["base_url"]),
                          json={"choices": [{"finish_reason": finish, "message": {"content": content}}]})


class DecodeAndParseTests(unittest.TestCase):
    def test_decode_accepts_small_png_jpeg_and_data_uri(self):
        self.assertEqual(decode_image(B64_PNG)[1], "image/png")
        self.assertEqual(decode_image(base64.b64encode(JPEG).decode())[1], "image/jpeg")
        self.assertEqual(decode_image("data:image/png;base64," + B64_PNG)[1], "image/png")

    def test_decode_rejects_other_files_bad_base64_and_large_images(self):
        self.assertIsNone(decode_image(base64.b64encode(b"%PDF-1.7 not an image").decode()))
        self.assertIsNone(decode_image("not base64!!"))
        big = PNG + b"\x00" * MAX_IMAGE_BYTES
        self.assertIsNone(decode_image(base64.b64encode(big).decode()))

    def test_parse_cleans_dedupes_and_limits(self):
        text = '```json\n{"brands": ["스타벅스", " 스타벅스 ", "STARBUCKS", "https://evil.example", "' + "가" * 31 + '", 3, "a", "b", "c", "d"]}\n```'
        self.assertEqual(parse_brands(text), ["스타벅스", "STARBUCKS", "a", "b", "c"])

    def test_parse_rejects_non_json_or_wrong_shape(self):
        for text in ["스타벅스", '["스타벅스"]', '{"names": []}']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_brands(text)


class BrandOCRAPITests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_returns_candidates_with_registered_first_and_sends_image_once(self):
        with patch("app.brand_ocr.baze_settings", return_value=SETTINGS), \
             patch("httpx.AsyncClient.post", AsyncMock(return_value=ai_reply('{"brands": ["메가커피", "스타벅스"]}'))) as post:
            data = self.client.post("/api/ocr/brands", json={"image_base64": B64_PNG}).json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["brands"], [{"name": "스타벅스", "registered": True}, {"name": "메가커피", "registered": False}])
        self.assertEqual(post.await_count, 1)
        sent = post.call_args.kwargs["json"]
        image_part = sent["messages"][1]["content"][1]["image_url"]["url"]
        self.assertTrue(image_part.startswith("data:image/png;base64,"))
        self.assertNotIn("test-only-key", json.dumps(sent))

    def test_english_alias_offers_registered_canonical_candidate(self):
        with patch("app.brand_ocr.baze_settings", return_value=SETTINGS), \
             patch("httpx.AsyncClient.post", AsyncMock(return_value=ai_reply('{"brands": ["STARBUCKS COFFEE", "NAVERX"]}'))):
            data = self.client.post("/api/ocr/brands", json={"image_base64": B64_PNG}).json()
        self.assertIn({"name": "스타벅스", "registered": True}, data["brands"])
        self.assertIn({"name": "NAVERX", "registered": False}, data["brands"])
        self.assertNotIn("ocr_confidence", data)

    def test_empty_result_has_message(self):
        with patch("app.brand_ocr.baze_settings", return_value=SETTINGS), \
             patch("httpx.AsyncClient.post", AsyncMock(return_value=ai_reply('{"brands": []}'))):
            data = self.client.post("/api/ocr/brands", json={"image_base64": B64_PNG}).json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["brands"], [])
        self.assertIn("찾지 못했어요", data["message"])

    def test_invalid_image_never_calls_ai(self):
        with patch("app.brand_ocr.baze_settings", return_value=SETTINGS), patch("httpx.AsyncClient.post", AsyncMock()) as post:
            data = self.client.post("/api/ocr/brands", json={"image_base64": base64.b64encode(b"GIF89a....").decode()}).json()
        self.assertEqual(data["status"], "invalid_image")
        post.assert_not_called()

    def test_failures_and_missing_key_are_unavailable(self):
        cases = [
            ({**SETTINGS, "api_key": ""}, AsyncMock()),
            (SETTINGS, AsyncMock(side_effect=httpx.ReadTimeout("timeout"))),
            (SETTINGS, AsyncMock(return_value=ai_reply("스타벅스입니다"))),
            (SETTINGS, AsyncMock(return_value=ai_reply('{"brands": ["스타"', finish="length"))),
        ]
        for settings, post in cases:
            with self.subTest(post=post), patch("app.brand_ocr.baze_settings", return_value=settings), \
                 patch("httpx.AsyncClient.post", post):
                data = self.client.post("/api/ocr/brands", json={"image_base64": B64_PNG}).json()
            self.assertEqual(data["status"], "unavailable")
            self.assertEqual(data["message"], UNAVAILABLE_MESSAGE)

    def test_request_size_is_limited(self):
        response = self.client.post("/api/ocr/brands", json={"image_base64": "A" * 4_300_001})
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
