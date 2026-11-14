import copy
import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from app.domain_ai import PROMPT, WEAK_EVIDENCE_REASON, _parse_response, verify_official_domains
from app.main import app
from tests.test_verdict import complete_response, metadata

SETTINGS = {"api_key": "test-domain-key", "base_url": "https://gateway.example/v1/gateway", "model": "gpt-6-luna"}


def check(host="kakao.com", status="official", relationship="exact"):
    return {"hostname": host, "status": status, "organization": "카카오",
            "official_domains": ["kakao.com", "kakaocorp.com"],
            "source_urls": ["https://www.kakaocorp.com/ownership", "https://registry.gov/kakao"],
            "relationship": relationship, "reason": "검색한 공식 기관 자료에 근거한 판정이에요."}


def payload(checks=None):
    checks = [check()] if checks is None else checks
    return {"status": "completed", "output": [
        {"type": "web_search_call", "status": "completed", "action": {
            "sources": [{"url": "https://www.kakaocorp.com/ownership"}, {"url": "https://registry.gov/kakao"}]}},
        {"type": "message", "role": "assistant", "content": [
            {"type": "output_text", "text": json.dumps({"checks": checks}), "annotations": []}]}]}


def response(data):
    return httpx.Response(200, request=httpx.Request("POST", SETTINGS["base_url"] + "/responses/"), json=data)


class DomainParsingTests(unittest.TestCase):
    def test_searched_official_and_lookalike_answers_have_provenance(self):
        reports = _parse_response(payload([check(), check("kaka0.com", "impersonation", "lookalike")]),
                                  ["kakao.com", "kaka0.com"], SETTINGS["model"])
        self.assertEqual(reports["kakao.com"]["status"], "matched")
        self.assertEqual(reports["kaka0.com"]["status"], "mismatched")
        self.assertEqual(reports["kaka0.com"]["legal_status"], "not_assessed")
        self.assertEqual(len(reports["kakao.com"]["sources"]), 2)

    def test_regulatory_disclosure_sources_can_corroborate_official_domain(self):
        item = check("www.kakaocorp.com")
        item["source_urls"] = ["https://englishdart.fss.or.kr/company", "https://kind.krx.co.kr/filing"]
        data = payload([item])
        data["output"][0]["action"]["sources"] = [{"url": u} for u in item["source_urls"]]
        result = _parse_response(data, [item["hostname"]], SETTINGS["model"])
        self.assertEqual(result[item["hostname"]]["status"], "matched")

    def test_without_actual_search_a_model_claim_is_rejected(self):
        data = payload()
        data["output"] = data["output"][1:]
        with self.assertRaises(ValueError):
            _parse_response(data, ["kakao.com"], SETTINGS["model"])

    def test_invented_sources_and_self_attestation_cannot_establish_official_status(self):
        cases = []
        invented = check()
        invented["source_urls"] = ["https://invented.com/proof"]
        cases.append(payload([invented]))
        own = check()
        own["official_domains"] = ["kakao.com"]
        own["source_urls"] = ["https://kakao.com/about"]
        own_data = payload([own])
        own_data["output"][0]["action"]["sources"] = [{"url": "https://kakao.com/about"}]
        cases.append(own_data)
        for data in cases:
            with self.subTest(data=data):
                self.assertEqual(_parse_response(data, ["kakao.com"], SETTINGS["model"])["kakao.com"]["status"], "unknown")

    def test_different_legitimate_domain_is_not_automatically_impersonation(self):
        item = check("booking.com", "impersonation", "unrelated")
        result = _parse_response(payload([item]), ["booking.com"], SETTINGS["model"])
        self.assertEqual(result["booking.com"]["status"], "unknown")

    def test_unsupported_official_domain_relationship_is_not_accepted(self):
        item = check("kakao.com.evil.com")
        self.assertEqual(_parse_response(payload([item]), [item["hostname"]], SETTINGS["model"])[item["hostname"]]["status"], "unknown")
        item = check("kakao.com", "official", "unrelated")
        self.assertEqual(_parse_response(payload([item]), ["kakao.com"], SETTINGS["model"])["kakao.com"]["status"], "unknown")
        item = check("kakao.com", "impersonation", "lookalike")
        self.assertEqual(_parse_response(payload([item]), ["kakao.com"], SETTINGS["model"])["kakao.com"]["status"], "unknown")

    def test_duplicate_missing_hosts_and_incomplete_responses_are_rejected(self):
        for data, hosts in [(payload([check(), check()]), ["kakao.com", "kaka0.com"]),
                            (payload(), ["kakao.com", "kaka0.com"]),
                            ({**payload(), "status": "incomplete"}, ["kakao.com"])]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                _parse_response(data, hosts, SETTINGS["model"])


class DomainNetworkTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        p = patch.dict("os.environ", {"BAZE_DOMAIN_MODEL": ""})
        p.start()
        self.addCleanup(p.stop)

    async def test_batch_is_fresh_and_transmits_hosts_only_without_paths_or_tokens(self):
        result = payload([check(), check("kaka0.com", "impersonation", "lookalike")])
        with patch("app.domain_ai.baze_settings", return_value=SETTINGS), \
             patch("httpx.AsyncClient.post", AsyncMock(return_value=response(result))) as post:
            for _ in range(2):
                reports = await verify_official_domains(
                    ["https://kakao.com/private?token=never-send#private-fragment", "https://kaka0.com/path"],
                    ["카카오"])
                self.assertEqual(reports["kakao.com"]["status"], "matched")
            self.assertEqual(post.await_count, 2)  # Every scan searches again, no result cache.
            body = post.call_args.kwargs["json"]
            sent = json.dumps(body, ensure_ascii=False)
            for secret in ["private", "never-send", "token=", "test-domain-key"]:
                self.assertNotIn(secret, sent)
            self.assertEqual(json.loads(body["input"]), {"domains": ["kakao.com", "kaka0.com"], "brand_hints": ["카카오"]})
            self.assertEqual(body["max_tool_calls"], 2)
            self.assertFalse(body["store"])
            self.assertEqual(body["tools"][0]["type"], "web_search")

    async def test_same_host_deduplicates_and_disabled_or_ip_never_calls_ai(self):
        with patch("httpx.AsyncClient.post", AsyncMock()) as post:
            report = await verify_official_domains(["https://kakao.com/a", "https://kakao.com/b"], enabled=False)
            self.assertEqual(list(report), ["kakao.com"])
            self.assertEqual(report["kakao.com"]["ai_status"], "disabled")
            self.assertEqual(await verify_official_domains(["https://127.0.0.1", "https://internal.local"]), {})
            post.assert_not_called()

    async def test_missing_configuration_never_falls_back_to_json(self):
        with patch("app.domain_ai.baze_settings", return_value={**SETTINGS, "api_key": ""}), \
             patch("httpx.AsyncClient.post", AsyncMock()) as post:
            result = await verify_official_domains(["https://kakao.com"])
        self.assertEqual(result["kakao.com"]["status"], "unknown")
        post.assert_not_called()

    async def test_provider_errors_and_unsupported_search_return_unknown_without_leaking_details(self):
        forbidden = httpx.Response(403, request=httpx.Request("POST", SETTINGS["base_url"]),
                                  json={"error": {"message": "private-upstream-body"}})
        for reply in [forbidden, response({"status": "completed", "output": []})]:
            with self.subTest(reply=reply), patch("app.domain_ai.baze_settings", return_value=SETTINGS), \
                 patch("httpx.AsyncClient.post", AsyncMock(return_value=reply)):
                result = await verify_official_domains(["https://kakao.com"])
                self.assertEqual(result["kakao.com"]["status"], "unknown")
                self.assertNotIn("private-upstream-body", json.dumps(result))

    @staticmethod
    def self_only():
        """The model says official, but cites only the checked site itself (fails the evidence check)."""
        own = check()
        own["source_urls"] = ["https://kakao.com/about", "https://kakao.com/company"]
        data = payload([own])
        data["output"][0]["action"]["sources"] = [{"url": u} for u in own["source_urls"]]
        return data

    async def test_self_only_sources_retry_once_with_evidence_note_and_accept_grounded_answer(self):
        replies = [response(self.self_only()), response(payload())]
        with patch("app.domain_ai.baze_settings", return_value=SETTINGS), \
             patch("httpx.AsyncClient.post", AsyncMock(side_effect=replies)) as post:
            result = await verify_official_domains(["https://kakao.com"])
        self.assertEqual(result["kakao.com"]["status"], "matched")
        self.assertEqual(post.await_count, 2)
        first, second = (c.kwargs["json"] for c in post.call_args_list)
        self.assertEqual(first["instructions"], PROMPT)
        self.assertTrue(second["instructions"].startswith(PROMPT) and "RETRY" in second["instructions"])
        self.assertEqual(second["input"], first["input"])  # Same hosts only; nothing new leaves the server.

    async def test_retry_that_is_still_weak_or_fails_keeps_first_unknown(self):
        failed = httpx.Response(500, request=httpx.Request("POST", SETTINGS["base_url"]), json={})
        for second in [response(self.self_only()), failed]:
            with self.subTest(second=second.status_code), patch("app.domain_ai.baze_settings", return_value=SETTINGS), \
                 patch("httpx.AsyncClient.post", AsyncMock(side_effect=[response(self.self_only()), second])) as post:
                result = await verify_official_domains(["https://kakao.com"])
            self.assertEqual(result["kakao.com"]["status"], "unknown")
            self.assertEqual(result["kakao.com"]["reason"], WEAK_EVIDENCE_REASON)
            self.assertEqual(post.await_count, 2)

    async def test_no_retry_for_grounded_answers_genuine_unknown_or_without_time_budget(self):
        genuine = check(status="unknown", relationship="unknown")
        for data, budget in [(payload(), 50), (payload([genuine]), 50), (self.self_only(), 0)]:
            with self.subTest(budget=budget), patch("app.domain_ai.baze_settings", return_value=SETTINGS), \
                 patch("app.domain_ai.TOTAL_BUDGET", budget), \
                 patch("httpx.AsyncClient.post", AsyncMock(return_value=response(data))) as post:
                await verify_official_domains(["https://kakao.com"])
            self.assertEqual(post.await_count, 1)

    def test_prompt_states_the_independent_source_rule(self):
        self.assertIn("EVIDENCE RULE", PROMPT)
        self.assertIn("DIFFERENT registered domain", PROMPT)

    async def test_timeout_returns_unknown(self):
        with patch("app.domain_ai.baze_settings", return_value=SETTINGS), \
             patch("httpx.AsyncClient.post", AsyncMock(side_effect=httpx.ReadTimeout("private detail"))):
            result = await verify_official_domains(["https://kakao.com"])
        self.assertEqual(result["kakao.com"]["ai_status"], "unavailable")


class DomainAPITests(unittest.TestCase):
    def setUp(self):
        p = patch.dict("os.environ", {"BAZE_DOMAIN_MODEL": ""})
        p.start()
        self.addCleanup(p.stop)

    def test_new_brand_not_in_registry_is_scored_from_search_in_both_api_routes(self):
        data = payload([check("kaka0.com", "impersonation", "lookalike")])
        with patch("app.domain_ai.baze_settings", return_value=SETTINGS), \
             patch("app.main.analyze_url", AsyncMock(return_value=copy.deepcopy(metadata("https://kaka0.com")))), \
             patch("httpx.AsyncClient.post", AsyncMock(return_value=response(data))) as post, \
             patch("app.services.url_analysis.compare_brand_domain", side_effect=AssertionError("Must not read brand DB")), \
             patch("app.services.domain_keywords._brand_words", side_effect=AssertionError("Must not read brand DB")), TestClient(app) as client:
            combined = client.post("/api/analyze", json={"qr_text": "https://kaka0.com", "brand_texts": ["카카오"]})
            standalone = client.post("/api/url/analyze", json={"qr_text": "https://kaka0.com", "include_ai": True})
        self.assertEqual(combined.status_code, 200)
        self.assertEqual(standalone.status_code, 200)
        self.assertEqual(combined.json()["verdict"]["score"], 50)
        self.assertEqual(combined.json()["verdict"]["level"], "위험")
        self.assertEqual(standalone.json()["brand_domain"]["status"], "mismatched")
        self.assertEqual(post.await_count, 2)
        self.assertFalse(combined.json()["auto_open"])

    def test_ai_opt_out_leaves_official_domain_unknown_instead_of_using_registry(self):
        with patch("app.main.analyze_url", AsyncMock(return_value=metadata("https://naver.com"))), \
             patch("httpx.AsyncClient.post", AsyncMock()) as post, TestClient(app) as client:
            data = client.post("/api/analyze", json={
                "qr_text": "https://naver.com", "brand_texts": ["네이버"], "include_ai": False}).json()
        self.assertEqual(data["url_analysis"]["brand_domain"]["status"], "unknown")
        self.assertEqual(data["url_analysis"]["brand_domain"]["source"], "ai_web_search")
        self.assertEqual(data["verdict"]["assessment_status"], "partial")
        post.assert_not_called()

    def test_unknown_domain_blocks_low_verdict_even_with_complete_other_checks_and_no_hint(self):
        url = "https://unverified.com"
        inspected = complete_response(url)
        inspected["page"].update(ai_model="mock-behavior", ai_assessment="no_obvious_signals", final_url=url)
        with patch("app.main.analyze_url", AsyncMock(return_value=metadata(url))), \
             patch("app.main.inspect_page", AsyncMock(return_value=inspected)), \
             patch("app.main.verify_official_domains", AsyncMock(return_value={})) as search, TestClient(app) as client:
            data = client.post("/api/analyze", json={
                "qr_text": url, "brand_texts": [], "inspect_page": True}).json()
        self.assertEqual(data["verdict"]["score"], 0)
        self.assertEqual(data["verdict"]["level"], "확인 불가")
        self.assertEqual(data["verdict"]["assessment_status"], "partial")
        search.assert_awaited_once_with([url, None], [], enabled=True)

    def test_blocked_public_hostname_does_not_trigger_external_domain_search(self):
        url = "https://blocked.com"
        blocked = metadata(url)
        blocked["navigation_allowed"] = False
        blocked["evidence"]["dns"]["status"] = "blocked"
        with patch("app.main.analyze_url", AsyncMock(return_value=blocked)), \
             patch("httpx.AsyncClient.post", AsyncMock()) as post, TestClient(app) as client:
            data = client.post("/api/analyze", json={"qr_text": url, "brand_texts": []}).json()
        self.assertEqual(data["verdict"]["level"], "위험")
        self.assertEqual(data["url_analysis"]["brand_domain"]["ai_status"], "disabled")
        post.assert_not_called()
