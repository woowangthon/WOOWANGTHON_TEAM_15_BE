import copy
import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from app.ai import AI_UNAVAILABLE_REASON, _cache, explain_result
from app.main import app
from app.security import score_result

RESULT = {
    "url": "https://example.com/?token=private-secret",
    "hostname": "example.com",
    "score": 25,
    "level": "주의",
    "reasons": [{"code": "NEW_DOMAIN", "points": 25, "message": "도메인이 생성된 지 30일 미만입니다."}],
    "evidence": {"dns": {"status": "ok", "addresses": ["8.8.8.8"]},
                 "rdap": {"status": "ok"}, "tls": {"status": "ok"}, "geoip": {"status": "unknown"}},
    "analysis_complete": False, "navigation_allowed": True, "auto_open": False,
    "requires_confirmation": True, "warning": "안전을 보장하지 않습니다.",
}
RESULT["evidence"]["rdap"]["age_days"] = 3
RESULT.update(score_result(RESULT["url"], RESULT["hostname"], RESULT["evidence"]))

SETTINGS = {"api_key": "test-only-key", "base_url": "https://gateway.example/v1/gateway", "model": "gpt-6-luna"}


class AITests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        _cache.clear()

    async def test_minimal_payload_and_cache(self):
        original = copy.deepcopy(RESULT)
        response = httpx.Response(200, request=httpx.Request("POST", SETTINGS["base_url"]),
                                 json={"choices": [{"finish_reason": "stop", "message": {"content": "생성된 지 얼마 안 된 도메인입니다. 접속 전 확인하세요."}}]})
        with patch("app.ai.baze_settings", return_value=SETTINGS), patch("httpx.AsyncClient.post", AsyncMock(return_value=response)) as post:
            first = await explain_result(RESULT)
            second = await explain_result(RESULT)
            self.assertEqual(first["ai_status"], "generated")
            self.assertEqual(second["ai_status"], "cached")
            self.assertEqual(post.await_count, 1)
            body = post.call_args.kwargs["json"]
            serialized = json.dumps(body)
            for value in ["private-secret", "example.com", "8.8.8.8", "test-only-key"]:
                self.assertNotIn(value, serialized)
            self.assertEqual(body["max_tokens"], 512)
            self.assertEqual(RESULT, original)

    async def test_disabled_blocked_and_missing_configuration_skip_network(self):
        blocked = {**RESULT, "navigation_allowed": False}
        with patch("app.ai.baze_settings", return_value={**SETTINGS, "api_key": ""}), patch("httpx.AsyncClient.post", AsyncMock()) as post:
            disabled = await explain_result(RESULT, enabled=False)
            self.assertEqual(disabled["ai_status"], "disabled")
            self.assertIsNone(disabled.get("skip_reason"))
            self.assertEqual((await explain_result(blocked))["ai_status"], "skipped")
            missing = await explain_result(RESULT)
            self.assertEqual(missing["ai_status"], "unavailable")
            self.assertEqual(missing["skip_reason"], AI_UNAVAILABLE_REASON)
            post.assert_not_called()

    async def test_blocked_target_skips_ai_and_gives_reason(self):
        cases = [
            ({"evidence": {**RESULT["evidence"], "dns": {"status": "blocked", "addresses": []}}}, "내부 기기를 가리키는 주소"),
            ({"page": {"status": "blocked", "reason": "HTTPS에서 HTTP로의 이동을 차단했습니다."}}, "보안 연결이 없는 주소"),
            ({"page": {"status": "blocked", "reason": "잘못된 이동 주소입니다."}}, "안전하지 않은 주소"),
            ({"page": {"status": "ok"}}, "내부 기기 주소로 넘어가려"),
        ]
        for extra, phrase in cases:
            with self.subTest(phrase=phrase), patch("app.ai.baze_settings", return_value=SETTINGS), \
                 patch("httpx.AsyncClient.post", AsyncMock()) as post:
                result = await explain_result({**RESULT, "navigation_allowed": False, **extra})
                self.assertEqual(result["ai_status"], "skipped")
                self.assertIn(phrase, result["skip_reason"])
                self.assertIn("AI 설명을 만들지 않아요", result["skip_reason"])
                post.assert_not_called()

    async def test_failures_preserve_fallback(self):
        for failure in [httpx.ReadTimeout("timeout"), TimeoutError(), ValueError("bad response")]:
            with self.subTest(failure=type(failure).__name__), patch("app.ai.baze_settings", return_value=SETTINGS), patch("httpx.AsyncClient.post", AsyncMock(side_effect=failure)):
                result = await explain_result(RESULT)
                self.assertEqual(result["ai_status"], "unavailable")
                self.assertIn("일부", result["ai_explanation"])
                self.assertEqual(result["skip_reason"], AI_UNAVAILABLE_REASON)
                self.assertEqual(len(_cache), 0)

    async def test_truncated_and_malformed_response_fall_back(self):
        for payload in [{}, {"choices": []}, {"choices": [{"finish_reason": "length", "message": {"content": "partial"}}]}]:
            response = httpx.Response(200, request=httpx.Request("POST", SETTINGS["base_url"]), json=payload)
            with self.subTest(payload=payload), patch("app.ai.baze_settings", return_value=SETTINGS), patch("httpx.AsyncClient.post", AsyncMock(return_value=response)):
                result = await explain_result(RESULT)
                self.assertEqual(result["ai_status"], "unavailable")
                self.assertEqual(result["skip_reason"], AI_UNAVAILABLE_REASON)

    async def test_expired_cache_and_rotated_key_do_not_reuse_result(self):
        response = httpx.Response(200, request=httpx.Request("POST", SETTINGS["base_url"]),
                                 json={"choices": [{"finish_reason": "stop", "message": {"content": "접속 전 확인하세요."}}]})
        with patch("app.ai.baze_settings", return_value=SETTINGS), patch("httpx.AsyncClient.post", AsyncMock(return_value=response)) as post:
            await explain_result(RESULT)
            for key, (_, text) in list(_cache.items()):
                _cache[key] = (0, text)
            await explain_result(RESULT)
            self.assertEqual(post.await_count, 2)
        with patch("app.ai.baze_settings", return_value={**SETTINGS, "api_key": "rotated-test-key"}), patch("httpx.AsyncClient.post", AsyncMock(return_value=response)) as post:
            self.assertEqual((await explain_result(RESULT))["ai_status"], "generated")
            self.assertEqual(post.await_count, 1)


class APIAITests(unittest.TestCase):
    def test_api_explanation_and_opt_out(self):
        with patch("app.main.analyze_url", AsyncMock(return_value=copy.deepcopy(RESULT))), patch("httpx.AsyncClient.post", AsyncMock()) as post, TestClient(app) as client:
            response = client.post("/api/analyze", json={"qr_text": RESULT["url"], "brand_texts": [], "include_ai": False})
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["score"], RESULT["score"])
            self.assertEqual(payload["level"], RESULT["level"])
            self.assertEqual(payload["ai_status"], "disabled")
            self.assertFalse(payload["auto_open"])
            self.assertEqual(payload["explanation_status"], "disabled")
            self.assertEqual(payload["explanation"], payload["ai_explanation"])
            post.assert_not_called()

    def test_explanation_is_opt_in(self):
        with patch("app.main.analyze_url", AsyncMock(return_value=copy.deepcopy(RESULT))), \
             patch("app.ai.baze_settings", return_value=SETTINGS), \
             patch("httpx.AsyncClient.post", AsyncMock()) as post, TestClient(app) as client:
            payload = client.post("/api/analyze", json={"qr_text": RESULT["url"], "brand_texts": []}).json()
            self.assertEqual(payload["explanation_status"], "disabled")
            post.assert_not_called()

    def test_api_explanation_includes_url_signals_without_url_text(self):
        _cache.clear()
        text = "단축 URL이라 실제 목적지를 알 수 없고, 실행 파일을 내려받게 합니다. 접속 전 확인하세요."
        response = httpx.Response(200, request=httpx.Request("POST", SETTINGS["base_url"]),
                                 json={"choices": [{"finish_reason": "stop", "message": {"content": text}}]})
        url = "https://bit.ly/private-path/setup.apk?token=private-secret"
        metadata = {**copy.deepcopy(RESULT), "url": url, "hostname": "bit.ly"}
        with patch("app.main.analyze_url", AsyncMock(return_value=metadata)), \
             patch("app.ai.baze_settings", return_value=SETTINGS), \
             patch("httpx.AsyncClient.post", AsyncMock(return_value=response)) as post, TestClient(app) as client:
            payload = client.post("/api/analyze", json={
                "qr_text": url, "brand_texts": ["테스트브랜드"], "include_explanation": True}).json()
        self.assertEqual(payload["explanation_status"], "generated")
        self.assertEqual(payload["explanation"], text)
        self.assertEqual(payload["explanation_model"], SETTINGS["model"])
        # The explanation never changes the scored result.
        self.assertEqual(payload["score"], RESULT["score"])
        self.assertEqual(payload["level"], RESULT["level"])
        self.assertEqual(post.await_count, 1)
        sent = json.loads(post.call_args.kwargs["json"]["messages"][1]["content"])
        self.assertEqual(sent["url_signals"]["pattern_codes"], ["SHORT_URL", "EXECUTABLE_LINK"])
        self.assertEqual(sent["url_signals"]["brand_domain_status"], "mismatched")
        # The explanation follows the overall (combined-v1) verdict the screen shows.
        self.assertEqual(sent["overall"]["level"], payload["verdict"]["level"])
        self.assertEqual(sent["overall"]["level"], "위험")
        self.assertIn("EXECUTABLE_DOWNLOAD", [r["code"] for r in sent["overall"]["reasons"]])
        serialized = json.dumps(post.call_args.kwargs["json"], ensure_ascii=False)
        for value in ["bit.ly", "private-path", "private-secret", "테스트브랜드", "test-only-key", "8.8.8.8"]:
            self.assertNotIn(value, serialized)


if __name__ == "__main__":
    unittest.main()
