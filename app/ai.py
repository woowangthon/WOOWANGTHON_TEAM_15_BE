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
SYSTEM_PROMPT = (
    "QR 보안 검사 결과를 쉬운 한국어 2~3문장으로 설명하세요. "
    "제공된 근거만 사용하고 점수와 등급을 변경하지 마세요. "
    "조회 실패를 안전으로 해석하거나 악성·안전을 확정하지 마세요. "
    "마지막에는 자동 접속하지 말고 사용자 확인이 필요하다고 안내하세요. "
    "웹 검색, 링크, 마크다운, 분석 과정은 출력하지 마세요."
)


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
    return {
        "score": result["score"],
        "level": result["level"],
        "reasons": [{"code": r["code"], "message": r["message"]} for r in result["reasons"]],
        "checks": {name: item["status"] for name, item in result["evidence"].items()},
        "analysis_complete": result["analysis_complete"],
    }


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
    fingerprint = json.dumps([settings["api_key"], settings["base_url"], settings["model"], summary])
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
