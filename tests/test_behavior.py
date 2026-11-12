import copy
import json
import unittest

from app.behavior import ATTACK_TYPES, unknown_attacks, validate_assessment
from app.page_content import inspect_html
from app.scoring import combine_page, score_metadata

NORMAL_EVIDENCE = {"dns": {"status": "ok"}, "rdap": {"status": "ok", "age_days": 10},
                   "tls": {"status": "ok"}, "geoip": {"status": "ok"}}


def base(evidence=None):
    checks = copy.deepcopy(NORMAL_EVIDENCE if evidence is None else evidence)
    return {"url": "https://example.com", "hostname": "example.com", "evidence": checks,
            **score_metadata("https://example.com", checks)}


def attacks(kind="credential_theft", severity="strong", ids=None):
    return [{"type": item, "severity": severity if item == kind else "none",
             "evidence_ids": (ids or ["page_text_1", "form_1"]) if item == kind and severity not in {"none", "unknown"} else []}
            for item in ATTACK_TYPES]


def page(classifications, status="generated"):
    return {"status": "ok", "ai_status": status, "attack_types": classifications, "findings": [], "evidence": []}


class BehaviorScoreTests(unittest.TestCase):
    def test_proposed_example_60_plus_15_is_75(self):
        result = combine_page(base(), page(attacks()))
        self.assertEqual(result["score"], 75)
        self.assertEqual(result["components"], {"ai_behavior": 60, "tls": 0, "domain_age": 15})
        self.assertEqual(result["assessment_status"], "complete")
        self.assertEqual(result["score_version"], "behavior-v1")
        self.assertEqual(sum(r["points"] for r in result["reasons"]), 75)

    def test_attack_categories_do_not_double_count(self):
        classifications = attacks()
        classifications[1] = {"type": "personal_data_theft", "severity": "strong", "evidence_ids": ["page_text_2"]}
        self.assertEqual(combine_page(base(), page(classifications))["score"], 75)

    def test_none_unknown_failed_and_partial_are_distinct(self):
        result = combine_page(base(), page(attacks(severity="none")))
        self.assertEqual(result["components"]["ai_behavior"], 0)
        self.assertEqual(result["assessment_status"], "complete")
        result = combine_page(base(), page(unknown_attacks()))
        self.assertIsNone(result["components"]["ai_behavior"])
        self.assertEqual(result["assessment_status"], "partial")
        result = combine_page(base(), page(unknown_attacks(), "unavailable"))
        self.assertEqual(result["score"], 15)
        self.assertEqual(result["assessment_status"], "partial")
        failed = {k: {"status": "unknown"} for k in NORMAL_EVIDENCE}
        result = score_metadata("https://example.com", failed)
        self.assertIsNone(result["score"])
        self.assertEqual(result["assessment_status"], "failed")
        self.assertEqual(result["level"], "확인 불가")

    def test_tls_and_domain_caps_and_source_target_deduplication(self):
        checks = copy.deepcopy(NORMAL_EVIDENCE)
        checks["tls"] = {"status": "invalid"}
        source = base(checks)
        result = combine_page(source, page(attacks()), base(checks))
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["components"]["tls"], 25)
        self.assertEqual(result["components"]["domain_age"], 15)
        self.assertEqual(sum(r["points"] for r in result["reasons"]), 100)

    def test_no_task_two_or_foreign_country_points(self):
        checks = copy.deepcopy(NORMAL_EVIDENCE)
        checks["rdap"]["age_days"] = 400
        checks["geoip"]["is_overseas"] = True
        result = score_metadata("https://bit.ly/app.apk", checks)
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["reasons"], [])

    def test_meta_refresh_or_unknown_category_does_not_claim_complete(self):
        report = page(attacks(severity="none"))
        report["meta_refresh"] = True
        self.assertEqual(combine_page(base(), report)["assessment_status"], "partial")
        categories = attacks(severity="none")
        categories[-1]["severity"] = "unknown"
        self.assertEqual(combine_page(base(), page(categories))["assessment_status"], "partial")


class BehaviorValidationTests(unittest.TestCase):
    def setUp(self):
        self.content = inspect_html('<p>긴급 계정 정지. 비밀번호와 OTP를 즉시 입력하여 인증하세요.</p><form><input type="password"></form>', "https://example.com")

    def validate(self, items):
        return validate_assessment(json.dumps({"attacks": items}), self.content["evidence"])

    def test_actual_evidence_references_validate(self):
        self.assertEqual(self.validate(attacks())[0]["severity"], "strong")

    def test_missing_repeated_and_invented_evidence_are_rejected(self):
        for items in [attacks()[:3], [attacks()[0]] * 4, attacks(ids=["invented_1"]), attacks(ids=["form_1", "form_1"])]:
            with self.subTest(items=items), self.assertRaises(ValueError):
                self.validate(items)

    def test_unsupported_category_and_structure_alone_cannot_be_strong(self):
        with self.assertRaises(ValueError):
            self.validate(attacks(kind="financial_fraud"))
        with self.assertRaises(ValueError):
            self.validate(attacks(ids=["form_1"]))

    def test_ordinary_login_and_educational_text_can_score_none(self):
        samples = [
            '<p>일반 로그인 페이지입니다.</p><form><input type="password"></form>',
            '<p>피싱 예방 안내: 비밀번호를 다른 사람에게 제출하지 마세요.</p>',
            '<p>Download and install our official software release.</p><a href="/app.exe">Download</a>',
        ]
        items = attacks(severity="none")
        for sample in samples:
            normal = inspect_html(sample, "https://example.com")
            self.assertEqual(len(validate_assessment(json.dumps({"attacks": items}), normal["evidence"])), 4)

    def test_unknown_evidence_and_arbitrary_score_fields_are_rejected(self):
        items = attacks(severity="unknown")
        items[0]["evidence_ids"] = ["page_text_1"]
        with self.assertRaises(ValueError):
            self.validate(items)
        with self.assertRaises(ValueError):
            validate_assessment(json.dumps({"attacks": attacks(), "score": 100}), self.content["evidence"])
