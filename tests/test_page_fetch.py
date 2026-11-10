import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.page_fetch import MAX_BYTES, PinnedResolver, fetch_page, request_html
from app.security import public_ip

PUBLIC = {"status": "ok", "addresses": ["8.8.8.8"]}


class FetchPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_private_target_and_redirect_are_never_requested(self):
        blocked = {"status": "blocked", "addresses": [], "reason": "private"}
        with patch("app.page_fetch.resolve", AsyncMock(return_value=blocked)), patch("app.page_fetch.request_html", AsyncMock()) as request:
            self.assertEqual((await fetch_page("https://127.0.0.1"))["status"], "blocked")
            request.assert_not_called()
        with patch("app.page_fetch.resolve", AsyncMock(side_effect=[PUBLIC, blocked])), patch("app.page_fetch.request_html", AsyncMock(return_value={"http_status": 302, "location": "https://169.254.169.254/"})) as request:
            self.assertEqual((await fetch_page("https://example.com"))["status"], "blocked")
            self.assertEqual(request.await_count, 1)

    async def test_rebinding_private_ip_fails_connector_resolver(self):
        with self.assertRaises(ValueError):
            PinnedResolver("example.com", ["8.8.8.8", "10.0.0.1"])
        resolver = PinnedResolver("example.com", ["8.8.8.8"])
        self.assertEqual((await resolver.resolve("example.com", 443))[0]["host"], "8.8.8.8")
        with self.assertRaises(OSError):
            await resolver.resolve("other.example", 443)
        self.assertFalse(public_ip("64:ff9b::7f00:1"))

    async def test_redirect_downgrade_and_credentials_are_blocked(self):
        for destination in ["http://example.com", "https://user:password@example.com", "file:///etc/passwd", "https://evil.example/\nheader"]:
            with self.subTest(destination=destination), patch("app.page_fetch.resolve", AsyncMock(return_value=PUBLIC)), patch("app.page_fetch.request_html", AsyncMock(return_value={"http_status": 302, "location": destination})) as request:
                self.assertEqual((await fetch_page("https://example.com"))["status"], "blocked")
                self.assertEqual(request.await_count, 1)

    async def test_redirect_limit_and_final_html(self):
        with patch("app.page_fetch.resolve", AsyncMock(return_value=PUBLIC)), patch("app.page_fetch.request_html", AsyncMock(side_effect=[{"http_status": 302, "location": f"/{i}"} for i in range(4)])) as request:
            self.assertEqual((await fetch_page("https://example.com"))["status"], "unknown")
            self.assertEqual(request.await_count, 4)
        with patch("app.page_fetch.resolve", AsyncMock(return_value=PUBLIC)), patch("app.page_fetch.request_html", AsyncMock(side_effect=[{"http_status": 302, "location": "/next"}, {"http_status": 200, "status": "ok", "html": "<p>Hello</p>"}])):
            result = await fetch_page("https://example.com")
            self.assertEqual(result["final_url"], "https://example.com/next")
            self.assertEqual(len(result["redirect_chain"]), 2)

    async def test_executable_path_and_timeout(self):
        with patch("app.page_fetch.resolve", AsyncMock(return_value=PUBLIC)), patch("app.page_fetch.request_html", AsyncMock()) as request:
            self.assertEqual((await fetch_page("https://example.com/file.%61pk"))["status"], "not_applicable")
            request.assert_not_called()
        with patch("app.page_fetch.resolve", AsyncMock(side_effect=TimeoutError())):
            self.assertEqual((await fetch_page("https://example.com"))["status"], "unknown")


class FakeResponse:
    def __init__(self, headers, chunks=(), status=200):
        self.headers = headers
        self.status = status
        self.charset = "utf-8"
        self.content = MagicMock()
        self.body_iterated = False
        async def iterator(_):
            self.body_iterated = True
            for chunk in chunks:
                yield chunk
        self.content.iter_chunked = iterator

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class ResponseLimitTests(unittest.IsolatedAsyncioTestCase):
    async def request(self, response):
        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        session.get.return_value = response
        with patch("aiohttp.ClientSession", return_value=session) as factory, patch("aiohttp.TCPConnector"):
            result = await request_html("https://example.com", "example.com", 443, ["8.8.8.8"])
            config = factory.call_args.kwargs
            self.assertFalse(config["trust_env"])
            self.assertFalse(config["auto_decompress"])
            self.assertFalse(session.get.call_args.kwargs["allow_redirects"])
            self.assertNotIn("Authorization", config["headers"])
            return result

    async def test_attachments_non_html_compression_and_size_skip_body(self):
        for headers in [
            {"Content-Disposition": "attachment; filename=x.apk", "Content-Type": "text/html"},
            {"Content-Type": "application/octet-stream"},
            {"Content-Type": "text/html", "Content-Encoding": "gzip"},
            {"Content-Type": "text/html", "Content-Length": str(MAX_BYTES + 1)},
        ]:
            with self.subTest(headers=headers):
                response = FakeResponse(headers)
                self.assertNotEqual((await self.request(response))["status"], "ok")
                self.assertFalse(response.body_iterated)

    async def test_chunked_body_size_is_also_limited(self):
        response = FakeResponse({"Content-Type": "text/html"}, [b"x" * MAX_BYTES, b"x"])
        self.assertEqual((await self.request(response))["status"], "unknown")
        response = FakeResponse({"Content-Type": "text/html"}, [b"<p>hello</p>"])
        self.assertEqual((await self.request(response))["html"], "<p>hello</p>")
