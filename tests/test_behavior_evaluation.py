import unittest

from app.behavior import ATTACK_TYPES
from scripts.evaluate_behavior import DEFAULT_CASES, grade_case, load_cases, summarize


def report(kind=None, severity="none", status="generated"):
    return {"ai_status":status,"attack_types":[{"type":item,"severity":severity if item==kind else "none"} for item in ATTACK_TYPES]}


class EvaluationTests(unittest.TestCase):
    def test_failures_and_unknown_are_not_counted_as_safe(self):
        case={"id":"normal","label":"benign"}
        for result in [report(status="unavailable"),report("credential_theft","unknown"),{"ai_status":"generated","attack_types":[]}]:
            row=grade_case(case,result)
            self.assertEqual(row["outcome"],"INCONCLUSIVE")
            self.assertIsNone(row["ai_points"])
            self.assertEqual(summarize([row])["confusion"]["TN"],0)

    def test_confusion_counts_and_expected_category_strength(self):
        benign={"id":"normal","label":"benign"}
        hostile={"id":"phish","label":"malicious","expected_attack":"credential_theft"}
        rows=[grade_case(benign,report()),grade_case(benign,report("financial_fraud","weak")),
              grade_case(hostile,report()),grade_case(hostile,report("credential_theft","strong"))]
        self.assertEqual(summarize(rows)["confusion"],{"TP":1,"TN":1,"FP":1,"FN":1})
        self.assertEqual(grade_case(hostile,report("financial_fraud","strong"))["outcome"],"FAIL")
        self.assertEqual(grade_case(hostile,report("credential_theft","weak"))["outcome"],"FAIL")

    def test_fixture_covers_benign_and_all_four_attack_categories(self):
        cases=load_cases(DEFAULT_CASES)
        self.assertEqual(len(cases),10)
        self.assertEqual(sum(case["label"]=="benign" for case in cases),6)
        self.assertEqual({case["expected_attack"] for case in cases if case["label"]=="malicious"},set(ATTACK_TYPES))


if __name__ == "__main__":
    unittest.main()
