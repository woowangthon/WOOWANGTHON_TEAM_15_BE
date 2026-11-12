"""Evaluate synthetic static HTML with the production AI classifier; never browse fixture URLs."""
import argparse
import asyncio
import json
from pathlib import Path

from app.behavior import ATTACK_TYPES, SEVERITY_POINTS
from app.config import baze_settings
from app.page_analysis import assess_content
from app.page_content import inspect_html

DEFAULT_CASES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "behavior_cases.json"


def load_cases(path):
    cases = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        raise ValueError("Expected a non-empty JSON list")
    seen = set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or case["id"] in seen:
            raise ValueError("Cases need unique string IDs")
        seen.add(case["id"])
        if case.get("label") not in {"benign", "malicious"} or not isinstance(case.get("html"), str):
            raise ValueError("Each case needs label benign/malicious and HTML text")
        if case["label"] == "malicious" and case.get("expected_attack") not in ATTACK_TYPES:
            raise ValueError("Malicious cases need a supported expected_attack")
    return cases


def grade_case(case, report):
    severities = {item["type"]: item["severity"] for item in report.get("attack_types", [])}
    complete = (report.get("ai_status") in {"generated", "cached"}
                and set(severities) == set(ATTACK_TYPES)
                and all(value in SEVERITY_POINTS and value != "unknown" for value in severities.values()))
    row = {"id": case["id"], "label": case["label"], "expected_attack": case.get("expected_attack"),
           "ai_status": report.get("ai_status"), "severities": severities}
    if not complete:
        return {**row, "outcome": "INCONCLUSIVE", "ai_points": None, "confusion": None}
    points = {kind: SEVERITY_POINTS[value] for kind, value in severities.items()}
    # Any nonzero behavior signal counts as a binary warning. Expected attacks
    # must reach moderate (30) to pass the stricter per-case classification check.
    predicted = max(points.values()) > 0
    expected = case["label"] == "malicious"
    confusion = "TP" if expected and predicted else "FN" if expected else "FP" if predicted else "TN"
    passed = points[case["expected_attack"]] >= 30 if expected else not predicted
    return {**row, "outcome": "PASS" if passed else "FAIL", "ai_points": max(points.values()), "confusion": confusion}


def summarize(rows):
    assessed = [row for row in rows if row["outcome"] != "INCONCLUSIVE"]
    return {"cases": len(rows), "passed": sum(row["outcome"] == "PASS" for row in rows),
            "failed": sum(row["outcome"] == "FAIL" for row in rows),
            "inconclusive": len(rows)-len(assessed),
            "coverage": len(assessed)/len(rows) if rows else None,
            "confusion": {key: sum(row["confusion"] == key for row in assessed) for key in ("TP", "TN", "FP", "FN")}}


async def evaluate(cases):
    rows = []
    for case in cases:
        # Fixed .example base only resolves relative HTML attributes locally.
        # No target HTTP, DNS, form submission, JavaScript or file execution.
        content = inspect_html(case["html"], "https://fixture.example/")
        row = grade_case(case, await assess_content(content, True))
        rows.append(row)
        print(json.dumps(row,ensure_ascii=True),flush=True)
    summary = summarize(rows)
    print(json.dumps({"summary": summary},ensure_ascii=True),flush=True)
    return 0 if summary["failed"] == 0 and summary["inconclusive"] == 0 else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES, help="Labeled static HTML cases JSON")
    parser.add_argument("--case", action="append", default=[], help="Run only this case ID; repeat for multiple IDs")
    parser.add_argument("--limit", type=int, help="Maximum selected cases")
    parser.add_argument("--live", action="store_true", help="Call the real BAZE API (uses tokens). Default only lists cases.")
    args = parser.parse_args()
    try:
        cases = load_cases(args.cases)
    except (OSError, ValueError, TypeError):
        parser.error("Cannot load valid labeled cases JSON")
    if args.case:
        if not set(args.case).issubset({case["id"] for case in cases}):
            parser.error("Unknown case ID")
        cases = [case for case in cases if case["id"] in args.case]
    if args.limit is not None:
        if args.limit < 1:
            parser.error("--limit must be positive")
        cases = cases[:args.limit]
    if not args.live:
        for case in cases:
            print(case["id"] + " expected=" + case["label"] + " " + case.get("expected_attack", ""))
        print("Preview only: no network or AI calls. Add --live to evaluate with BAZE.")
        return 0
    settings = baze_settings()
    if not settings["api_key"] or not settings["model"]:
        parser.error("Configure BAZE_API_KEY and BAZE_MODEL in the backend .env")
    print(json.dumps({"model":settings["model"],"selected_cases":len(cases),"score_scope":"AI behavior only; no TLS/domain/URL points"}),flush=True)
    return asyncio.run(evaluate(cases))


if __name__ == "__main__":
    raise SystemExit(main())
