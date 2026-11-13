"""Optional BAZE explanation of rule results; never changes the security verdict."""
import asyncio
import hashlib
import json
import re
import time
from collections import OrderedDict
from urllib.parse import urlsplit

import httpx

from app.config import baze_settings

CACHE_TTL = 600
CACHE_LIMIT = 128
_cache = OrderedDict()
# The output is shown as-is to the person who scanned the QR, so it must read as advice to them,
# not as instructions to the app (e.g. no "자동 접속하지 말고 사용자 확인").
SYSTEM_PROMPT = (
    "당신은 QR 코드를 찍은 일반 사용자에게 검사 결과를 알려주는 도우미입니다. "
    "입력 JSON은 서버가 QR 속 주소를 검사한 결과입니다. 이를 바탕으로 휴대폰 화면에 그대로 보여줄 "
    "쉬운 한국어 해요체(~해요, ~세요) 2~3문장을 쓰세요. '~습니다', '~합니다' 같은 합쇼체는 쓰지 마세요.\n"
    "규칙:\n"
    "1. 화면을 보는 사람에게 직접 말하세요. '사용자', '자동 접속', '시스템', '서버', '검사 결과는' 같은 "
    "내부 표현이나 3인칭 지시문을 쓰지 마세요.\n"
    "2. 점수 숫자, 등급 이름(낮음·주의·위험·확인 불가), 코드 이름, DNS·RDAP·TLS·GeoIP 같은 기술 용어를 "
    "쓰지 말고 쉬운 말로 바꾸세요. 예: TLS → 보안 연결, 도메인 생성일 → 사이트 주소가 만들어진 시기, "
    "SHORT_URL → 단축 주소, EXECUTABLE_LINK → 앱·실행 파일을 내려받는 주소, "
    "brand_domain_status=mismatched → 상표의 공식 주소와 다름, "
    "domain_impersonation_status=impersonation_suspected → 등록된 매장 주소를 흉내 낸 주소, "
    "printed_domain_status=mismatched → QR 주변 안내문에 적힌 주소와 QR 주소가 다름(가짜 QR 스티커가 덧붙여졌을 수 있지만 "
    "주문·예약 대행 서비스일 수도 있음), "
    "brand_in_domain=true → 유명 상표 이름이 들어간 주소지만 그 상표의 공식 주소가 아님, "
    "phishing_keyword_in_domain=true → 주소 이름에 로그인·인증·환불 같은 단어가 들어 있음.\n"
    "3. overall은 화면에 표시되는 최종 판정입니다. 말의 강도를 overall.level에 맞추세요. "
    "위험이면 들어가지 말라고 분명히 권하고, 주의면 확인을 권하고, 낮음이면 큰 위험 신호는 없었다고 말하되 "
    "안전을 보장하지 마세요. 바깥의 score·level은 일부 항목만 반영한 값이므로 overall과 다르면 overall을 따르세요.\n"
    "4. 입력에 있는 근거만 사용하세요. 위험 신호가 있으면 overall.reasons 중 가장 중요한 이유 1~2개를 먼저 말하세요. "
    "url_signals(주소 형태·공식 주소 비교·매장 주소 비교)와 page_attacks(페이지가 요구하는 행동)도 근거입니다.\n"
    "5. 확인하지 못한 항목(unknown 등)을 안전하다는 근거로 쓰지 마세요. "
    "안전하다거나 사기라고 단정하지 마세요. not_checked인 항목(요청하지 않아 하지 않은 검사)은 언급하지 마세요.\n"
    "6. 이미 확인된 좋은 결과는 그대로 알려 주고, 같은 것을 다시 확인하라고 하지 마세요. "
    "brand_domain_status=matched이면 '상표의 공식 주소와 일치해요'라고 말하고, "
    "'공식 사이트인지 확인하세요'나 '공식 앱이나 직접 검색한 주소로 들어가세요' 같은 말은 하지 마세요. "
    "store_qr_status=matched나 domain_impersonation_status=host_matched도 마찬가지입니다. "
    "printed_domain_status=matched이면 '안내문에 적힌 주소와 같아요'라고 말하세요.\n"
    "7. 마지막 문장은 남아 있는 위험에 맞는, 바로 할 수 있는 행동 하나로 끝내세요. "
    "예: 실행 파일 → 파일을 설치하지 않기, 공식 주소와 다름 → 공식 앱이나 직접 검색한 주소로 들어가기, "
    "안내문 주소와 다름 → QR 위에 스티커가 덧붙여져 있지 않은지 살펴보기, "
    "보안 연결 없음 → 비밀번호·카드번호를 입력하지 않기. "
    "남은 위험 신호가 없으면 '평소와 다르게 비밀번호나 결제 정보를 요구하면 입력하지 마세요'처럼 "
    "들어간 뒤에 조심할 점 하나를 알려 주세요.\n"
    "8. 링크, 마크다운, 목록 기호, 분석 과정은 출력하지 마세요."
)
# Shown in the result screen's AI card when the AI was not called for a blocked target.
BLOCKED_SKIP_REASONS = {
    "internal_address": "집·회사 내부 기기를 가리키는 주소라 이 앱에서 막았어요. 막힌 주소는 AI 설명을 만들지 않아요.",
    "https_to_http_redirect": "보안 연결이 없는 주소로 넘어가려 해서 이 앱에서 막았어요. 막힌 주소는 AI 설명을 만들지 않아요.",
    "unsafe_redirect": "안전하지 않은 주소로 넘어가려 해서 이 앱에서 막았어요. 막힌 주소는 AI 설명을 만들지 않아요.",
    "redirect_to_internal_address": "내부 기기 주소로 넘어가려 해서 이 앱에서 막았어요. 막힌 주소는 AI 설명을 만들지 않아요.",
}
# Shown in the AI card when the AI could not be reached (not configured, timeout, bad response).
AI_UNAVAILABLE_REASON = "지금은 AI 설명을 만들 수 없어요. 위 판정과 검사 항목을 확인해 주세요."
# Only status codes are forwarded: no hostname, path, QR/brand text or store name.
URL_SIGNAL_KEYS = ("pattern_codes", "brand_domain_status", "store_qr_status",
                   "domain_impersonation_status", "redirect_pattern_detected")

# Output filter: an explanation that breaks the prompt rules is dropped (shown as AI_UNAVAILABLE_REASON).
# Each entry is (problem code, pattern). Kept narrow so normal advice like "위험할 수 있어요" passes.
BANNED_PATTERNS = (
    ("INTERNAL_WORDING", re.compile(r"사용자|자동\s*접속|자동으로\s*접속|시스템|서버")),
    ("GRADE_OR_SCORE", re.compile(r"등급|확인\s*불가|점수|\d+\s*점")),
    ("TECH_TERM", re.compile(r"DNS|RDAP|TLS|SSL|GeoIP|geoip|WHOIS|[A-Z]{2,}_[A-Z_]+|[a-z]+_[a-z_]+")),
    ("FORMAL_ENDING", re.compile(r"(니다|니까)(?=[.!?\s]|$)")),
    ("LINK_OR_MARKDOWN", re.compile(r"https?://|www\.|\*\*|^\s*[-*•]\s|^\s*#", re.M)),
)
# Asking to double-check something the server already confirmed (e.g. brand matched).
RECHECK_CONFIRMED = re.compile(r"공식\s*(사이트|주소|도메인)인지|공식\s*앱이나\s*직접\s*검색")


def explanation_problems(text, summary):
    """Return rule-violation codes for an AI explanation; empty means it can be shown."""
    problems = [code for code, pattern in BANNED_PATTERNS if pattern.search(text)]
    signals = summary.get("url_signals") or {}
    if signals.get("brand_domain_status") == "matched" and RECHECK_CONFIRMED.search(text):
        problems.append("RECHECK_CONFIRMED")
    return problems


def fallback_text(result):
    reasons = [r["message"] for r in result["reasons"][:3]]
    detail = " ".join(reasons) if reasons else "현재 규칙에서 추가 위험 신호를 찾지 못했습니다."
    if result["score"] is None:
        detail = "위험도를 산출할 자료가 부족합니다."
    incomplete = "" if result["analysis_complete"] else " 일부 정보는 확인하지 못했습니다."
    label = f'{result["score"]}점' if result["score"] is not None else "점수 산출 불가"
    return f'{result["level"]}({label}): {detail}{incomplete} 안전을 보장하지 않으며, 접속 전 사용자 확인이 필요합니다.'


def summary_for_ai(result):
    # No hostname, URL, query strings, QR/brand text, raw certificates or IP addresses.
    summary = {
        "score": result["score"],
        "level": result["level"],
        "reasons": [{"code": r["code"], "message": r["message"]} for r in result["reasons"]],
        "checks": {name: item["status"] for name, item in result["evidence"].items()},
        "analysis_complete": result["analysis_complete"],
    }
    signals = (result.get("url_analysis") or {}).get("risk_signals")
    if signals:
        summary["url_signals"] = {key: signals.get(key) for key in URL_SIGNAL_KEYS}
    keywords = result.get("domain_keyword_check") or {}
    if keywords.get("brand_in_domain") or keywords.get("domain_keywords"):
        # Flags only; the words and domains themselves are not forwarded.
        flags = summary.setdefault("url_signals", {})
        flags["brand_in_domain"] = bool(keywords.get("brand_in_domain"))
        flags["phishing_keyword_in_domain"] = bool(keywords.get("domain_keywords"))
    printed = (result.get("printed_domain_check") or {}).get("status")
    if printed and printed != "not_checked":
        # Status only; the printed domains themselves are not forwarded.
        summary.setdefault("url_signals", {})["printed_domain_status"] = printed
    attacks = [{"type": a["type"], "severity": a["severity"]} for a in result.get("attack_types") or []
               if a.get("severity") not in {"none", "unknown"}]
    if attacks:
        summary["page_attacks"] = attacks
    verdict = result.get("verdict")
    if verdict:
        summary["overall"] = {"level": verdict["level"],
                              "reasons": [{"code": r["code"], "message": r["message"]} for r in verdict["reasons"]]}
    return summary


def blocked_kind(result):
    """Why the target was blocked, as a fixed category."""
    if (result.get("evidence") or {}).get("dns", {}).get("status") == "blocked":
        return "internal_address"
    page = result.get("page") or {}
    if page.get("status") == "blocked":
        return "https_to_http_redirect" if "HTTPS에서 HTTP" in (page.get("reason") or "") else "unsafe_redirect"
    return "redirect_to_internal_address"


async def request_explanation(settings, summary):
    """One raw AI call, before the output filter. Raises on HTTP errors or incomplete responses.
    Used by explain_result and by scripts/check_explanations.py (which needs the unfiltered text)."""
    body = {
        "model": settings["model"],
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": summary}],
        "max_tokens": 512,
        "stream": False,
    }
    if settings["model"].startswith("gpt-"):
        body["reasoning_effort"] = "low"
    async with httpx.AsyncClient(timeout=10, follow_redirects=False, trust_env=False) as client:
        response = await client.post(
            settings["base_url"] + "/chat/completions/",
            headers={"Authorization": "Bearer " + settings["api_key"]},
            json=body,
        )
        response.raise_for_status()
        choice = response.json()["choices"][0]
        text = choice["message"]["content"]
        if choice.get("finish_reason") != "stop" or not isinstance(text, str) or not text.strip() or len(text) > 600:
            raise ValueError("Incomplete or invalid explanation")
        return text.strip()


async def explain_result(result, enabled=True):
    fallback = {"ai_explanation": fallback_text(result), "ai_status": "disabled", "ai_model": None}
    if not enabled:
        return fallback
    if not result["navigation_allowed"]:
        # No AI call for blocked targets; the screen shows why instead.
        return {**fallback, "ai_status": "skipped", "skip_reason": BLOCKED_SKIP_REASONS[blocked_kind(result)]}
    settings = baze_settings()
    base = urlsplit(settings["base_url"])
    if (not settings["api_key"] or not settings["model"] or base.scheme != "https"
            or not base.hostname or base.username or base.password or base.query or base.fragment):
        return {**fallback, "ai_status": "unavailable", "skip_reason": AI_UNAVAILABLE_REASON}

    summary_data = summary_for_ai(result)
    summary = json.dumps(summary_data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    # Prompt is part of the key so a prompt change never serves explanations written under the old one.
    fingerprint = json.dumps([settings["api_key"], settings["base_url"], settings["model"], SYSTEM_PROMPT, summary])
    cache_key = hashlib.sha256(fingerprint.encode()).hexdigest()
    cached = _cache.get(cache_key)
    if cached and cached[0] > time.monotonic():
        _cache.move_to_end(cache_key)
        return {"ai_explanation": cached[1], "ai_status": "cached", "ai_model": settings["model"]}
    _cache.pop(cache_key, None)

    async def generate():
        text = await request_explanation(settings, summary)
        # Rule-breaking wording is never shown or cached; the screen gets AI_UNAVAILABLE_REASON instead.
        if explanation_problems(text, summary_data):
            raise ValueError("Explanation breaks output rules")
        return text

    try:
        text = await asyncio.wait_for(generate(), timeout=12)
    except (httpx.HTTPError, TimeoutError, ValueError, KeyError, IndexError, TypeError):
        # Do not log upstream responses or authorization headers.
        return {**fallback, "ai_status": "unavailable", "skip_reason": AI_UNAVAILABLE_REASON}

    _cache[cache_key] = (time.monotonic() + CACHE_TTL, text)
    while len(_cache) > CACHE_LIMIT:
        _cache.popitem(last=False)
    return {"ai_explanation": text, "ai_status": "generated", "ai_model": settings["model"]}
