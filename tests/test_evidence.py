import ssl
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.security import rdap_check, score_result, tls_check


class EvidenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_rdap_uses_registered_domain_and_ignores_invalid_dates(self):
        bootstrap = httpx.Response(200, request=httpx.Request("GET", "https://data.iana.org/rdap/dns.json"),
                                  json={"services": [[["kr"], ["https://rdap.example/"]]]})
        registration = httpx.Response(200, request=httpx.Request("GET", "https://rdap.example/domain/example.co.kr"),
                                      json={"events": [{"eventAction": "registration", "eventDate": "bad"},
                                                       {"eventAction": "registration", "eventDate": "2000-01-01"},
                                                       {"eventAction": "registration", "eventDate": "2000-01-01T00:00:00Z"}]})
        with patch("app.security._bootstrap_cache", None), patch("httpx.AsyncClient.get", AsyncMock(side_effect=[bootstrap, registration])) as get:
            result = await rdap_check("login.example.co.kr")
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["domain"], "example.co.kr")
            self.assertTrue(result["created_at"].startswith("2000-01-01"))
            self.assertEqual(get.call_args.args[0], "https://rdap.example/domain/example.co.kr")

    async def test_ip_rdap_is_not_applicable_and_sends_no_request(self):
        with patch("httpx.AsyncClient.get", AsyncMock()) as get:
            self.assertEqual((await rdap_check("8.8.8.8"))["status"], "not_applicable")
            get.assert_not_called()

    async def test_tls_connects_to_checked_ip_but_verifies_original_hostname(self):
        tls = MagicMock()
        tls.getpeercert.return_value = {"notAfter": "Jan  1 00:00:00 2030 GMT",
                                      "issuer": ((("organizationName", "Test CA"),),)}
        tls.version.return_value = "TLSv1.3"
        writer = MagicMock()
        writer.get_extra_info.return_value = tls
        writer.wait_closed = AsyncMock()
        with patch("asyncio.open_connection", AsyncMock(return_value=(MagicMock(), writer))) as connect:
            result = await tls_check("example.com", "8.8.8.8", 443)
            self.assertEqual(connect.call_args.args, ("8.8.8.8", 443))
            self.assertEqual(connect.call_args.kwargs["server_hostname"], "example.com")
            self.assertTrue(connect.call_args.kwargs["ssl"].check_hostname)
            self.assertEqual(result["issuer"], "Test CA")
            self.assertEqual(result["protocol"], "TLSv1.3")
            self.assertTrue(result["expires_at"].startswith("2030-01-01"))
            writer.close.assert_called_once()


class ScoreBoundaryTests(unittest.TestCase):
    def test_domain_age_boundaries_and_foreign_ip_does_not_add_points(self):
        for days, expected in [(29, 15), (30, 5), (179, 5), (180, 0)]:
            evidence = {"dns": {"status": "ok"}, "rdap": {"status": "ok", "age_days": days},
                        "tls": {"status": "ok"}, "geoip": {"status": "ok", "is_overseas": True}}
            with self.subTest(age_days=days):
                self.assertEqual(score_result("https://example.com", "example.com", evidence)["score"], expected)

    def test_task_two_url_patterns_do_not_add_points(self):
        evidence = {"dns": {"status": "ok"}, "rdap": {"status": "unknown"},
                    "tls": {"status": "ok"}, "geoip": {"status": "ok"}}
        result = score_result("https://bit.ly/file.%61pk", "bit.ly", evidence)
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["level"], "확인 불가")
        self.assertFalse(result["auto_open"])
