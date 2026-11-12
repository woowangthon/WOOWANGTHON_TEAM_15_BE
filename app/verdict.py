"""combined-v1: one overall verdict for the result screen and the AI explanation.

behavior-v1 (score/level/components) is left unchanged. This adds the URL/brand/store signals that
behavior-v1 deliberately excludes, so the screen, the score and the explanation say the same thing.

Rules
- Start from behavior-v1 components (AI behavior <=60, TLS <=25, domain age <=15).
- Add each URL signal at most once, checking both the scanned URL and the final URL after redirects
  (the worse of the two counts; nothing is added twice).
- Total is capped at 100. Level: >=50 위험, 20-49 주의, <20 낮음 only when behavior-v1 was complete,
  otherwise 확인 불가. A blocked target is always 위험.
"""

VERDICT_VERSION = "combined-v1"

# code: (points, message). Points are chosen so that a signal that is enough on its own to stop the
# user (download, fake brand/store domain, blocked hop) reaches 위험 (50), and a signal that only
# hides the destination reaches 주의 (20).
SIGNAL_POINTS = {
    "BLOCKED_NAVIGATION": (50, "내부 네트워크 주소이거나 안전하지 않은 이동이라 접속을 막았습니다."),
    "EXECUTABLE_DOWNLOAD": (50, "앱·실행 파일을 내려받게 하는 주소입니다."),
    "BRAND_DOMAIN_MISMATCH": (50, "상표의 공식 도메인과 다른 주소입니다."),
    "STORE_DOMAIN_IMPERSONATION": (50, "등록된 매장 주소를 흉내 낸 도메인입니다."),
    "STORE_QR_MISMATCH": (25, "등록된 매장 QR 주소와 다릅니다."),
    "SHORT_URL": (20, "단축 URL이라 실제 목적지를 숨길 수 있습니다."),
    "IP_LITERAL": (20, "도메인 대신 IP 주소를 사용합니다."),
    "REDIRECT_PARAMETER": (20, "다른 사이트로 넘겨주는 매개변수가 있습니다."),
}


def _signal_codes(url_analysis):
    if not url_analysis:
        return set()
    s = url_analysis.get("risk_signals") or {}
    patterns = set(s.get("pattern_codes") or [])
    codes = set()
    if patterns & {"EXECUTABLE_LINK", "EXECUTABLE_QUERY"}:
        codes.add("EXECUTABLE_DOWNLOAD")
    if "SHORT_URL" in patterns:
        codes.add("SHORT_URL")
    if "IP_LITERAL" in patterns:
        codes.add("IP_LITERAL")
    if s.get("redirect_pattern_detected"):
        codes.add("REDIRECT_PARAMETER")
    if s.get("brand_domain_status") == "mismatched":
        codes.add("BRAND_DOMAIN_MISMATCH")
    if s.get("domain_impersonation_status") == "impersonation_suspected":
        codes.add("STORE_DOMAIN_IMPERSONATION")
    elif s.get("store_qr_status") == "mismatched":
        codes.add("STORE_QR_MISMATCH")
    return codes


def combined_verdict(result):
    """result: the /api/analyze response (behavior-v1 fields + url_analysis/final_url_analysis/page)."""
    codes = _signal_codes(result.get("url_analysis")) | _signal_codes(result.get("final_url_analysis"))
    page = result.get("page") or {}
    if page.get("download_response"):
        codes.add("EXECUTABLE_DOWNLOAD")
    if not result.get("navigation_allowed", True):
        codes.add("BLOCKED_NAVIGATION")
    if "STORE_DOMAIN_IMPERSONATION" in codes:
        codes.discard("STORE_QR_MISMATCH")

    signal_reasons = [{"code": code, "points": SIGNAL_POINTS[code][0], "message": SIGNAL_POINTS[code][1]}
                      for code in SIGNAL_POINTS if code in codes]
    base_reasons = [{"code": r["code"], "points": r["points"], "message": r["message"]}
                    for r in result.get("reasons", []) if r.get("code") != "BLOCKED_TARGET"]

    known = [v for v in (result.get("components") or {}).values() if v is not None]
    signal_points = sum(r["points"] for r in signal_reasons)
    score = None if not known and not signal_reasons else min(100, sum(known) + signal_points)

    if "BLOCKED_NAVIGATION" in codes or (score is not None and score >= 50):
        level = "위험"
    elif score is not None and score >= 20:
        level = "주의"
    elif score is not None and result.get("assessment_status") == "complete":
        level = "낮음"
    else:
        level = "확인 불가"

    reasons = sorted(signal_reasons + base_reasons, key=lambda r: -r["points"])
    return {"version": VERDICT_VERSION, "score": score, "level": level, "reasons": reasons}
