"""Check AI result explanations against fixed QR cases before/after a prompt change.

For each case it runs the real /api/analyze pipeline in-process (DNS, TLS, page fetch, page AI),
then asks the explanation AI directly so the raw text is visible *before* the output filter, and reports:
- the overall verdict level vs the expected level
- each explanation text and the filter rules it breaks (app.ai.explanation_problems)
Default only lists cases. --live makes network requests and paid AI calls.

Usage (backend root):
  .\\.venv\\Scripts\\python.exe -B -m scripts.check_explanations
  .\\.venv\\Scripts\\python.exe -B -m scripts.check_explanations --live
  .\\.venv\\Scripts\\python.exe -B -m scripts.check_explanations --live --case naver_brand --repeat 3
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

DEFAULT_CASES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "explanation_cases.json"
LEVELS = {"낮음", "주의", "위험", "확인 불가", None}


def load_cases(path):
    cases = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        raise ValueError("Expected a non-empty JSON list")
    seen = set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or case["id"] in seen:
            raise ValueError("Cases need unique string IDs")
        seen.add(case["id"])
        if not isinstance(case.get("qr_text"), str) or not isinstance(case.get("brand_texts", []), list):
            raise ValueError("Each case needs qr_text and a brand_texts list")
        if case.get("expected_level") not in LEVELS:
            raise ValueError("expected_level must be 낮음/주의/위험/확인 불가 or null")
    return cases


def run_case(client, case, settings, repeat):
    from app.ai import explanation_problems, request_explanation, summary_for_ai

    body = {"qr_text": case["qr_text"], "brand_texts": case.get("brand_texts", []), "store_id": case.get("store_id"),
            "include_ai": True, "inspect_page": True, "include_explanation": False}
    response = client.post("/api/analyze", json=body)
    if response.status_code != 200:
        return {"id": case["id"], "outcome": "ERROR", "http_status": response.status_code}
    data = response.json()
    level = data["verdict"]["level"]
    expected = case.get("expected_level")
    row = {"id": case["id"], "level": level, "expected_level": expected,
           "level_ok": expected is None or level == expected, "outputs": []}
    if not data["navigation_allowed"]:
        # Same rule as explain_result: blocked targets never reach the AI.
        row["outcome"] = "PASS" if row["level_ok"] else "FAIL"
        row["note"] = "blocked: no AI call"
        return row

    summary = summary_for_ai(data)
    summary_json = json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    for _ in range(repeat):
        try:
            text = asyncio.run(request_explanation(settings, summary_json))
        except Exception as exc:  # noqa: BLE001 - report and continue; never print upstream bodies.
            row["outputs"].append({"text": None, "problems": ["AI_ERROR:" + type(exc).__name__]})
            continue
        row["outputs"].append({"text": text, "problems": explanation_problems(text, summary)})
    flagged = any(o["problems"] for o in row["outputs"])
    row["outcome"] = "PASS" if row["level_ok"] and not flagged else "FAIL"
    return row


def print_row(row):
    head = f"[{row['outcome']}] {row['id']}"
    if "level" in row:
        mark = "" if row["level_ok"] else f"  (expected {row['expected_level']})"
        head += f"  level={row['level']}{mark}"
    print(head)
    if row.get("note"):
        print("    " + row["note"])
    for i, output in enumerate(row.get("outputs", []), 1):
        problems = ", ".join(output["problems"]) or "ok"
        print(f"    {i}. [{problems}] {output['text'] or '-'}")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Check AI result explanations on fixed QR cases.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES, help="Cases JSON")
    parser.add_argument("--case", action="append", default=[], help="Run only this case ID; repeat for multiple IDs")
    parser.add_argument("--repeat", type=int, default=1, help="Explanation calls per case (AI output varies)")
    parser.add_argument("--json", action="store_true", help="Print one JSON object per case")
    parser.add_argument("--live", action="store_true", help="Make network requests and paid AI calls. Default only lists cases.")
    args = parser.parse_args()
    try:
        cases = load_cases(args.cases)
    except (OSError, ValueError, TypeError):
        parser.error("Cannot load valid explanation cases JSON")
    if args.case:
        if not set(args.case).issubset({c["id"] for c in cases}):
            parser.error("Unknown case ID")
        cases = [c for c in cases if c["id"] in args.case]
    if args.repeat < 1:
        parser.error("--repeat must be positive")
    if not args.live:
        for case in cases:
            print(f"{case['id']}: {case['qr_text']} brands={case.get('brand_texts', [])} expected={case.get('expected_level')}")
            print(f"    {case.get('note', '')}")
        print("Preview only: no network or AI calls. Add --live to run.")
        return 0

    from fastapi.testclient import TestClient

    from app.config import baze_settings
    from app.main import app

    settings = baze_settings()
    if not settings["api_key"] or not settings["model"]:
        parser.error("Configure BAZE_API_KEY and BAZE_MODEL in the backend .env")
    rows = []
    with TestClient(app) as client:
        for case in cases:
            row = run_case(client, case, settings, args.repeat)
            rows.append(row)
            if args.json:
                print(json.dumps(row, ensure_ascii=False), flush=True)
            else:
                print_row(row)
    outputs = [o for r in rows for o in r.get("outputs", [])]
    summary = {"cases": len(rows), "passed": sum(r["outcome"] == "PASS" for r in rows),
               "failed": sum(r["outcome"] != "PASS" for r in rows),
               "explanations": len(outputs), "flagged": sum(bool(o["problems"]) for o in outputs),
               "level_mismatch": sum(not r.get("level_ok", True) for r in rows)}
    print(json.dumps({"summary": summary}, ensure_ascii=False))
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
