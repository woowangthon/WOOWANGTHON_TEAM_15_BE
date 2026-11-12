"""Optional BAZE explanation of rule results; never changes the security verdict."""
import asyncio
import hashlib
import json
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
    "쉬운 한국어 해요체 2~3문장을 쓰세요.\n"
    "규칙:\n"
    "1. 화면을 보는 사람에게 직접 말하세요. '사용자', '자동 접속', '시스템', '서버', '검사 결과는' 같은 "
    "내부 표현이나 3인칭 지시문을 쓰지 마세요.\n"
    "2. 점수 숫자, 등급 이름(낮음·주의·위험·확인 불가), 코드 이름, DNS·RDAP·TLS·GeoIP 같은 기술 용어를 "
    "쓰지 말고 쉬운 말로 바꾸세요. 예: TLS → 보안 연결, 도메인 생성일 → 사이트 주소가 만들어진 시기, "
    "SHORT_URL → 단축 주소, EXECUTABLE_LINK → 앱·실행 파일을 내려받는 주소, "
    "brand_domain_status=mismatched → 상표의 공식 주소와 다름, "
    "domain_impersonation_status=impersonation_suspected → 등록된 매장 주소를 흉내 낸 주소.\n"
    "3. 입력에 있는 근거만 사용하세요. 위험 신호가 있으면 가장 중요한 이유 1~2개를 먼저 말하세요. "
    "url_signals(주소 형태·공식 주소 비교·매장 주소 비교)와 page_attacks(페이지가 요구하는 행동)도 근거입니다.\n"
    "4. 확인하지 못한 항목(unknown 등)을 안전하다는 근거로 쓰지 마세요. "
    "안전하다거나 사기라고 단정하지 마세요. not_checked인 항목(요청하지 않아 하지 않은 검사)은 언급하지 마세요.\n"
    "5. 마지막 문장은 사람이 바로 할 수 있는 구체적인 행동 하나로 끝내세요. "
    "예: 비밀번호·카드번호·인증번호를 입력하지 않기, 파일을 설치하지 않기, "
    "공식 앱이나 직접 검색한 주소로 들어가기.\n"
    "6. 링크, 마크다운, 목록 기호, 분석 과정은 출력하지 마세요."
)
# Only status codes are forwarded: no hostname, path, QR/brand text or store name.
URL_SIGNAL_KEYS = ("pattern_codes", "brand_domain_status", "store_qr_status",
                   "domain_impersonation_status", "redirect_pattern_detected")


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
    attacks = [{"type": a["type"], "severity": a["severity"]} for a in result.get("attack_types") or []
               if a.get("severity") not in {"none", "unknown"}]
    if attacks:
        summary["page_attacks"] = attacks
    return summary


async def explain_result(result, enabled=True):
    fallback = {"ai_explanation": fallback_text(result), "ai_status": "disabled", "ai_model": None}
    if not enabled:
        return fallback
    if not result["navigation_allowed"]:
        return {**fallback, "ai_status": "skipped"}
    settings = baze_settings()
    base = urlsplit(settings["base_url"])
    if (not settings["api_key"] or not settings["model"] or base.scheme != "https"
            or not base.hostname or base.username or base.password or base.query or base.fragment):
        return {**fallback, "ai_status": "unavailable"}

    summary = json.dumps(summary_for_ai(result), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    # Prompt is part of the key so a prompt change never serves explanations written under the old one.
    fingerprint = json.dumps([settings["api_key"], settings["base_url"], settings["model"], SYSTEM_PROMPT, summary])
    cache_key = hashlib.sha256(fingerprint.encode()).hexdigest()
    cached = _cache.get(cache_key)
    if cached and cached[0] > time.monotonic():
        _cache.move_to_end(cache_key)
        return {"ai_explanation": cached[1], "ai_status": "cached", "ai_model": settings["model"]}
    _cache.pop(cache_key, None)

    body = {
        "model": settings["model"],
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": summary}],
        "max_tokens": 512,
        "stream": False,
    }
    if settings["model"].startswith("gpt-"):
        body["reasoning_effort"] = "low"

    async def generate():
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

    try:
        text = await asyncio.wait_for(generate(), timeout=12)
    except (httpx.HTTPError, TimeoutError, ValueError, KeyError, IndexError, TypeError):
        # Do not log upstream responses or authorization headers.
        return {**fallback, "ai_status": "unavailable"}

    _cache[cache_key] = (time.monotonic() + CACHE_TTL, text)
    while len(_cache) > CACHE_LIMIT:
        _cache.popitem(last=False)
    return {"ai_explanation": text, "ai_status": "generated", "ai_model": settings["model"]}
