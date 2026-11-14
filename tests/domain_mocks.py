"""Explicit searched-domain fixtures for API integration tests; never used by production."""
from urllib.parse import urlsplit
from unittest.mock import AsyncMock, patch
from app.domain_ai import unknown_report

IMPERSONATIONS = {
    "nav3r.com": ("네이버", "naver.com"), "naevr.com": ("네이버", "naver.com"),
    "navr.com": ("네이버", "naver.com"), "edlya.com": ("이디야", "ediya.com"),
    "starbuks.co.kr": ("스타벅스", "starbucks.co.kr"),
    "naver-event.xyz": ("네이버", "naver.com"),
    "naver.com.login-check.xyz": ("네이버", "naver.com"),
    "naver-webtoon.example.com": ("네이버", "naver.com"),
}

async def searched_domains(urls, brand_texts=(), *, enabled=True):
    reports = {}
    for url in urls:
        if not url:
            continue
        host = urlsplit(url).hostname
        if not host or host == "127.0.0.1":
            continue
        if not enabled:
            reports[host] = unknown_report("공식 도메인 AI 검색을 수행하지 않았어요.", "disabled")
            continue
        if host in {"secure-login-verify.com", "login.example.org"}:
            reports[host] = unknown_report("공식 검색 근거가 부족한 테스트 사례", "generated")
            continue
        brand, official = IMPERSONATIONS.get(host, ("네이버" if "naver" in host else "테스트기관", host))
        reports[host] = {"status": "mismatched" if host in IMPERSONATIONS else "matched",
                         "brand": brand, "reason": "검색 출처에 근거한 테스트 판정",
                         "source": "ai_web_search", "ai_status": "generated", "ai_model": "mock-domain-model",
                         "official_domains": [official], "sources": ["https://registry.gov/organization"],
                         "relationship": "lookalike" if host in IMPERSONATIONS else "exact",
                         "legal_status": "not_assessed"}
    return reports

def install_domain_mock(test, *, standalone=False):
    mocked = AsyncMock(side_effect=searched_domains)
    for target in (["app.main.verify_official_domains", "app.routers.url_analysis.verify_official_domains"]
                   if standalone else ["app.main.verify_official_domains"]):
        p = patch(target, mocked)
        p.start()
        test.addCleanup(p.stop)
    return mocked
