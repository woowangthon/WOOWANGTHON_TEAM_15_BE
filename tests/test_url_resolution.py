import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.page_fetch import request_html
from tests.test_combined_analysis import metadata
from tests.test_page_fetch import FakeResponse, PUBLIC


class URLResolutionAPITests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def post(self, **extra):
        return self.client.post("/api/url/analyze", json={
            "qr_text": "https://bit.ly/demo", "brand_texts": ["네이버"],
            "resolve_redirects": True, **extra,
        })

    def test_opt_in_preserves_original_and_analyzes_final_url_without_ai(self):
        for code in [301, 302, 303, 307, 308]:
            with self.subTest(code=code), patch("app.page_fetch.resolve", AsyncMock(return_value=PUBLIC)), \
                 patch("app.page_fetch.request_html", AsyncMock(side_effect=[
                     {"http_status": code, "location": "https://m.naver.com/event"},
                     {"http_status": 200, "status": "ok", "bytes_read": 0},
                 ])) as request, patch("httpx.AsyncClient.post", AsyncMock()) as paid:
                response = self.post()
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertEqual(data["url_info"]["hostname"], "bit.ly")
                self.assertEqual(data["risk_signals"]["pattern_codes"], ["SHORT_URL"])
                self.assertEqual(data["url_resolution"]["final_url"], "https://m.naver.com/event")
                self.assertEqual(data["url_resolution"]["status"], "ok")
                self.assertFalse(data["url_resolution"]["body_inspected"])
                self.assertFalse(data["url_resolution"]["auto_open"])
                self.assertTrue(data["url_resolution"]["requires_confirmation"])
                self.assertEqual(data["final_url_analysis"]["brand_domain"]["status"], "matched")
                self.assertEqual(len(data["url_resolution"]["redirect_chain"]), 2)
                self.assertTrue(all(call.kwargs == {"headers_only": True} for call in request.await_args_list))
                paid.assert_not_called()

    def test_default_and_invalid_inputs_never_resolve(self):
        with patch("app.routers.url_analysis.resolve_url", AsyncMock()) as resolve:
            data = self.post(resolve_redirects=False).json()
            self.assertNotIn("url_resolution", data)
            self.assertNotIn("final_url_analysis", data)
            self.assertEqual(self.post(qr_text="not-a-url").json()["status"], "invalid_url")
            resolve.assert_not_called()

    def test_file_destination_is_analyzed_without_requesting_or_downloading_it(self):
        final = "https://example.com/setup.apk"
        with patch("app.page_fetch.resolve", AsyncMock(return_value=PUBLIC)), \
             patch("app.page_fetch.request_html", AsyncMock(return_value={"http_status": 302, "location": final})) as request:
            data = self.post().json()
        self.assertEqual(request.await_count, 1)
        self.assertEqual(data["url_resolution"]["status"], "not_applicable")
        self.assertEqual(data["url_resolution"]["final_url"], final)
        self.assertIn("EXECUTABLE_LINK", data["final_url_analysis"]["risk_signals"]["pattern_codes"])

    def test_private_redirect_and_unsafe_schemes_never_reach_target(self):
        blocked = {"status": "blocked", "addresses": [], "reason": "private"}
        with patch("app.page_fetch.resolve", AsyncMock(side_effect=[PUBLIC, blocked])), \
             patch("app.page_fetch.request_html", AsyncMock(return_value={
                 "http_status": 302, "location": "https://127.0.0.1/secret"})) as request:
            data = self.post().json()
        self.assertEqual(request.await_count, 1)
        self.assertEqual(data["url_resolution"]["status"], "blocked")
        self.assertIsNone(data["final_url_analysis"])
        for target in ["file:///etc/passwd", "https://user:pass@example.com", "http://example.com", "https://example.com/\nheader"]:
            with self.subTest(target=target), patch("app.page_fetch.resolve", AsyncMock(return_value=PUBLIC)), \
                 patch("app.page_fetch.request_html", AsyncMock(return_value={"http_status": 302, "location": target})) as request:
                data = self.post().json()
                self.assertEqual(data["url_resolution"]["status"], "blocked")
                self.assertIsNone(data["final_url_analysis"])
                self.assertEqual(request.await_count, 1)

    def test_relative_redirect_loop_limit_missing_location_and_timeout(self):
        with patch("app.page_fetch.resolve", AsyncMock(return_value=PUBLIC)), \
             patch("app.page_fetch.request_html", AsyncMock(side_effect=[
                 {"http_status": 302, "location": "/next"}, {"http_status": 200, "status": "ok"},
             ])):
            self.assertEqual(self.post().json()["url_resolution"]["final_url"], "https://bit.ly/next")
        scenarios = [
            [{"http_status": 302, "location": "/demo"}],
            [{"http_status": 302}],
            [{"http_status": 302, "location": f"/hop/{i}"} for i in range(4)],
        ]
        for replies in scenarios:
            with patch("app.page_fetch.resolve", AsyncMock(return_value=PUBLIC)), \
                 patch("app.page_fetch.request_html", AsyncMock(side_effect=replies)) as request:
                data = self.post().json()
                self.assertEqual(data["url_resolution"]["status"], "unknown")
                self.assertIsNone(data["final_url_analysis"])
                self.assertLessEqual(request.await_count, 4)
        with patch("app.page_fetch.resolve", AsyncMock(side_effect=TimeoutError())):
            self.assertEqual(self.post().json()["url_resolution"]["status"], "unknown")

    def test_non_success_response_does_not_claim_resolution_complete(self):
        with patch("app.page_fetch.resolve", AsyncMock(return_value=PUBLIC)), \
             patch("app.page_fetch.request_html", AsyncMock(return_value={
                 "http_status": 403, "status": "unknown", "reason": "access denied"})):
            data = self.post().json()
        self.assertEqual(data["url_resolution"]["status"], "unknown")
        self.assertIsNone(data["final_url_analysis"])

    def test_combined_analysis_checks_final_file_url_even_when_body_is_not_inspected(self):
        source, final = "https://bit.ly/demo", "https://example.com/setup.apk"
        with patch("app.main.analyze_url", AsyncMock(return_value=metadata(source))), \
             patch("app.page_analysis.analyze_url", AsyncMock(return_value=metadata(final))), \
             patch("app.page_analysis.fetch_page", AsyncMock(return_value={
                 "status": "not_applicable", "final_url": final, "reason": "file",
                 "redirect_chain": [{"url": source, "http_status": 302}],
             })), patch("httpx.AsyncClient.post", AsyncMock()) as paid:
            data = self.client.post("/api/analyze", json={
                "qr_text": source, "brand_texts": [], "inspect_page": True, "include_ai": False,
            }).json()
        self.assertIn("EXECUTABLE_LINK", data["final_url_analysis"]["risk_signals"]["pattern_codes"])
        self.assertIn("EXECUTABLE_DOWNLOAD", [reason["code"] for reason in data["verdict"]["reasons"]])
        paid.assert_not_called()


class HeaderOnlyRequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_binary_attachment_body_is_never_read(self):
        response = FakeResponse({"Content-Type": "application/octet-stream", "Content-Disposition": "attachment"}, [b"binary"])
        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        session.get.return_value = response
        with patch("aiohttp.ClientSession", return_value=session) as factory, patch("aiohttp.TCPConnector"):
            result = await request_html("https://example.com", "example.com", 443, PUBLIC["addresses"], headers_only=True)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["bytes_read"], 0)
        self.assertTrue(result["download_response"])
        self.assertFalse(response.body_iterated)
        self.assertFalse(session.get.call_args.kwargs["allow_redirects"])
        self.assertFalse(factory.call_args.kwargs["trust_env"])
