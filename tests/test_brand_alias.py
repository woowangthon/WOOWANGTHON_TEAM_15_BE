import copy
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient
from tests.domain_mocks import install_domain_mock

from app.main import app
from app.services.brand_alias import expand_brand_texts, find_registered
from tests.test_brand_ocr import B64_PNG, SETTINGS, ai_reply
from tests.test_verdict import metadata

BRANDS = ["테스트브랜드", "스타벅스", "이디야", "이디야커피", "네이버", "naver"]


class FindRegisteredTests(unittest.TestCase):
    def test_contained_brand_is_found(self):
        for text, expected in [
            ("네이버", "네이버"),
            ("네이버 웹툰", "네이버"),
            ("네이버웹툰", "네이버"),
            ("스타벅스 강남점", "스타벅스"),
            ("NAVER Pay", "naver"),
            ("naver/쇼핑", "naver"),
            ("이디야커피 신메뉴", "이디야커피"),  # longest registered name wins
            ("이디야 커피", "이디야커피"),  # spaces ignored: same brand as the registered "이디야커피"
            ("이디야 강남점", "이디야"),
        ]:
            with self.subTest(text=text):
                self.assertEqual(find_registered(text, BRANDS), expected)

    def test_unrelated_or_partial_latin_words_do_not_match(self):
        for text in ["메가커피", "naverx", "NaverPay", "웹툰 네이", "", None]:
            with self.subTest(text=text):
                self.assertIsNone(find_registered(text, BRANDS))

    def test_expand_keeps_original_and_adds_registered_once(self):
        with patch("app.services.brand_alias.registered_brands", return_value=BRANDS):
            self.assertEqual(expand_brand_texts(["네이버 웹툰", "NAVER Pay"]), ["네이버 웹툰", "NAVER Pay", "네이버", "naver"])
            self.assertEqual(expand_brand_texts(["네이버", "네이버 웹툰"]), ["네이버", "네이버 웹툰"])
            self.assertEqual(expand_brand_texts(["메가커피"]), ["메가커피"])


class AliasAPITests(unittest.TestCase):
    def setUp(self):
        self.domain_search = install_domain_mock(self)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_analyze_compares_contained_brand(self):
        for url, status in [("https://comic.naver.com", "matched"), ("https://naver-webtoon.example.com", "mismatched")]:
            with self.subTest(url=url), patch("app.main.analyze_url", AsyncMock(return_value=copy.deepcopy(metadata(url)))), \
                 patch("httpx.AsyncClient.post", AsyncMock()):
                data = self.client.post("/api/analyze", json={"qr_text": url, "brand_texts": ["네이버 웹툰"]}).json()
            self.assertEqual(data["url_analysis"]["risk_signals"]["brand_domain_status"], status)
            self.assertEqual(data["url_analysis"]["brand_domain"]["brand"], "네이버")

    def test_ocr_offers_registered_brand_first(self):
        with patch("app.brand_ocr.baze_settings", return_value=SETTINGS), \
             patch("httpx.AsyncClient.post", AsyncMock(return_value=ai_reply('{"brands": ["네이버 웹툰"], "domains": []}'))):
            data = self.client.post("/api/ocr/brands", json={"image_base64": B64_PNG}).json()
        self.assertEqual(data["brands"], [{"name": "네이버", "registered": True}, {"name": "네이버 웹툰", "registered": False}])


if __name__ == "__main__":
    unittest.main()
