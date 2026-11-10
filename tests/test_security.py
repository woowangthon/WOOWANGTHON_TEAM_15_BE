import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from app.main import app
from app.security import parse_url, public_ip, score_result, analyze_url, rdap_check, tls_check, resolve


class SecurityTests(unittest.TestCase):
    def test_invalid_inputs(self):
        for value in ["hello", "javascript:alert(1)", "https://user:pass@example.com",
                      "https://example.com:22", "https://example.com/\nhello", "https://bad_host.com"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_url(value)

    def test_normalization(self):
        self.assertEqual(parse_url(" HTTPS://Example.COM./path?q=1 ")[0], "https://example.com/path?q=1")
        self.assertEqual(parse_url("https://sub.example.co.kr")[1], "sub.example.co.kr")

    def test_private_and_reserved(self):
        for ip in ["127.0.0.1", "10.0.0.1", "::1", "169.254.169.254", "0.0.0.0", "224.0.0.1", "::ffff:127.0.0.1"]:
            self.assertFalse(public_ip(ip), ip)
        self.assertTrue(public_ip("8.8.8.8"))

    def test_scoring(self):
        evidence = {"dns": {"status": "ok"}, "rdap": {"status": "ok", "age_days": 3},
                    "tls": {"status": "invalid"}, "geoip": {"status": "ok"}}
        result = score_result("https://example.com/app.apk", "example.com", evidence)
        self.assertEqual(result["score"], 85)
        self.assertEqual(result["level"], "위험")
        evidence["rdap"] = {"status": "unknown"}
        evidence["tls"] = {"status": "ok"}
        self.assertEqual(score_result("https://example.com", "example.com", evidence)["level"], "확인 불가")

    def test_api_validation(self):
        with TestClient(app) as client:
            self.assertEqual(client.get("/health").json(), {"status": "ok"})
            self.assertEqual(client.post("/api/analyze", json={"qr_text": "bad", "brand_texts": []}).status_code, 422)
            self.assertEqual(client.post("/api/analyze", json={"qr_text": "https://example.com"}).status_code, 422)


class AsyncSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_blocked_does_not_probe(self):
        with patch("app.security.resolve", AsyncMock(return_value={"status": "blocked", "addresses": []})), patch("app.security.rdap_check", AsyncMock()) as rdap, patch("app.security.tls_check", AsyncMock()) as tls:
            result = await analyze_url("https://127.0.0.1")
            rdap.assert_not_called()
            tls.assert_not_called()
            self.assertFalse(result["navigation_allowed"])
            self.assertFalse(result["auto_open"])

    async def test_mixed_dns_blocked(self):
        records = [(2, 1, 6, "", ("8.8.8.8", 443)), (2, 1, 6, "", ("127.0.0.1", 443))]
        loop = __import__("asyncio").get_running_loop()
        with patch.object(loop, "getaddrinfo", AsyncMock(return_value=records)):
            self.assertEqual((await resolve("example.com", 443))["status"], "blocked")

    async def test_rdap_timeout_is_unknown(self):
        import httpx
        with patch("httpx.AsyncClient.get", AsyncMock(side_effect=httpx.ReadTimeout("timeout"))):
            self.assertEqual((await rdap_check("sub.example.co.kr"))["status"], "unknown")

    async def test_tls_certificate_failure(self):
        import ssl
        with patch("asyncio.open_connection", AsyncMock(side_effect=ssl.SSLCertVerificationError("bad cert"))):
            self.assertEqual((await tls_check("example.com", "8.8.8.8", 443))["status"], "invalid")

    async def test_success_contract(self):
        with patch("app.security.resolve", AsyncMock(return_value={"status": "ok", "addresses": ["8.8.8.8"]})), patch("app.security.rdap_check", AsyncMock(return_value={"status": "ok", "age_days": 400})), patch("app.security.tls_check", AsyncMock(return_value={"status": "ok", "valid": True})), patch("app.security.country_check", return_value={"status": "unknown"}):
            result = await analyze_url("https://example.com")
            self.assertEqual(result["level"], "확인 불가")
            self.assertTrue(result["requires_confirmation"])


if __name__ == "__main__":
    unittest.main()
