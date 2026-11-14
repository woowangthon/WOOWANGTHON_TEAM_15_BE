import copy
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app.ai import AI_UNAVAILABLE_REASON, _cache, explain_result, explanation_problems
from tests.test_ai import RESULT, SETTINGS

MATCHED = {"url_signals": {"brand_domain_status": "matched"}}
NO_BRAND = {"url_signals": {"brand_domain_status": "unknown"}}


class ExplanationFilterTests(unittest.TestCase):
    def test_good_explanations_pass(self):
        for text in [
            "상표의 공식 주소와 일치해요. 평소와 다르게 비밀번호나 결제 정보를 요구하면 입력하지 마세요.",
            "이 주소는 앱이나 실행 파일을 내려받게 해서 위험할 수 있어요. 파일을 설치하지 마세요.",
            "보안 연결을 사용하지 않아요. 비밀번호나 카드번호를 입력하지 마세요.",
            "단축 주소라 실제 목적지를 알 수 없어요. 들어가기 전에 주의하세요.",
        ]:
            with self.subTest(text=text):
                self.assertEqual(explanation_problems(text, MATCHED), [])

    def test_rule_breaking_explanations_are_flagged(self):
        for text, code in [
            ("자동으로 접속하지 말고 사용자 확인 후 진행하세요.", "INTERNAL_WORDING"),
            ("서버에서 검사한 결과 문제가 없어요.", "INTERNAL_WORDING"),
            ("등급은 낮음이에요.", "GRADE_OR_SCORE"),
            ("위험 점수는 0점이에요.", "GRADE_OR_SCORE"),
            ("일부 항목은 확인 불가예요.", "GRADE_OR_SCORE"),
            ("TLS 인증서가 유효해요.", "TECH_TERM"),
            ("SHORT_URL 신호가 있어요.", "TECH_TERM"),
            ("brand_domain_status가 일치해요.", "TECH_TERM"),
            ("공식 주소와 일치합니다.", "FORMAL_ENDING"),
            ("안전하지 않을 수 있습니다", "FORMAL_ENDING"),
            ("https://example.com 으로 들어가세요.", "LINK_OR_MARKDOWN"),
            ("**주의**하세요.", "LINK_OR_MARKDOWN"),
            ("- 파일을 설치하지 마세요.", "LINK_OR_MARKDOWN"),
        ]:
            with self.subTest(text=text):
                self.assertIn(code, explanation_problems(text, NO_BRAND))

    def test_recheck_of_confirmed_brand_is_flagged_only_when_matched(self):
        text = "상표의 공식 주소와 일치해요. 그래도 공식 사이트인지 확인해 주세요."
        self.assertIn("RECHECK_CONFIRMED", explanation_problems(text, MATCHED))
        self.assertNotIn("RECHECK_CONFIRMED", explanation_problems(text, NO_BRAND))
        advice = "공식 주소와 달라요. 공식 앱이나 직접 검색한 주소로 들어가세요."
        self.assertEqual(explanation_problems(advice, {"url_signals": {"brand_domain_status": "mismatched"}}), [])
        self.assertIn("RECHECK_CONFIRMED", explanation_problems(advice, MATCHED))


class ExplanationFilterIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        _cache.clear()

    async def test_rule_breaking_ai_text_is_dropped_and_not_cached(self):
        bad = httpx.Response(200, request=httpx.Request("POST", SETTINGS["base_url"]),
                             json={"choices": [{"finish_reason": "stop", "message": {"content": "자동 접속하지 말고 사용자 확인이 필요합니다."}}]})
        with patch("app.ai.baze_settings", return_value=SETTINGS), patch("httpx.AsyncClient.post", AsyncMock(return_value=bad)):
            result = await explain_result(copy.deepcopy(RESULT))
        self.assertEqual(result["ai_status"], "unavailable")
        self.assertEqual(result["skip_reason"], AI_UNAVAILABLE_REASON)
        self.assertEqual(len(_cache), 0)


if __name__ == "__main__":
    unittest.main()
