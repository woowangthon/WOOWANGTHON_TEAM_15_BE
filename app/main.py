import asyncio
import os
from typing import Annotated, Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app import config  # Load backend-local .env before reading settings.
from app.security import analyze_url, parse_url
from app.ai import explain_result, fallback_text
from app.brand_ocr import read_brands
from app.models import AnalyzeResponse
from app.page_analysis import inspect_page
from app.routers.url_analysis import router as url_analysis_router
from app.domain_ai import verify_official_domains, apply_domain_report, apply_domain_keyword_reports
from app.services.domain_keywords import check_domain_keywords
from app.services.printed_domain import compare_printed_domains
from app.services.url_analysis import analyze_url_signals
from app.verdict import combined_verdict
from app.scoring import metadata_only_result
from app.routers.ocr import router as ocr_router
from app.routers.qr import router as qr_router
from app.middleware.ocr_upload import OCRUploadLimitMiddleware
from app.errors import ApiError, install_error_handlers

app = FastAPI(title="QR Alert API", version="0.7.0")
install_error_handlers(app)
app.add_middleware(OCRUploadLimitMiddleware)
origins = [s.strip() for s in os.getenv("CORS_ORIGINS", "").split(",") if s.strip()]
if origins:
    app.add_middleware(CORSMiddleware, allow_origins=origins,
                       allow_methods=["POST", "GET"], allow_headers=["Content-Type"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class AnalyzeRequest(BaseModel):
    qr_text: str = Field(min_length=1, max_length=4096, description="QR에서 읽은 HTTP(S) URL")
    include_ai: bool = Field(default=True, description="공식 도메인 AI 검색·페이지 AI 참고 분석 사용 여부. 페이지 AI는 점수에서 제외")
    inspect_page: bool = Field(default=False, description="대상 사이트에 제한된 GET 요청을 보내 정적 HTML을 분석합니다.")
    brand_texts: list[str] = Field(max_length=30, description="OCR 등으로 인식한 브랜드명. URL의 공식 도메인 비교에 사용")
    store_id: str | None = Field(default=None, min_length=1, max_length=128, description="매장 검색 결과의 ID. 생략하면 매장 검사를 수행하지 않음")
    include_explanation: bool = Field(default=False, description="검사 결과를 쉬운 문장으로 설명하는 AI 호출 여부. include_ai=false이면 호출하지 않음")
    printed_domains: list[Annotated[str, Field(max_length=253)]] = Field(
        default_factory=list, max_length=10,
        description="QR 주변에 인쇄된 웹 주소(사진 OCR 결과). QR 주소와 같은 사이트인지 비교. 생략하면 비교하지 않음")


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse()


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest):
    # Validate both URL contracts before DNS, target-page or paid AI requests.
    try:
        url, _, _, _ = parse_url(request.qr_text)
    except ValueError as exc:
        raise ApiError(422, str(exc), code="INVALID_URL") from exc
    # AI interprets raw OCR/user names; no local brand aliases or official-domain list.
    brand_texts = [text.strip() for text in request.brand_texts if text.strip()]
    local = await asyncio.to_thread(analyze_url_signals, url, brand_texts, request.store_id, compare_brand=False)
    if not local["url_info"]["valid"]:
        raise ApiError(422, local["url_info"].get("reason", "잘못된 URL입니다."), code="INVALID_URL")
    result = await analyze_url(url)
    final_local = None
    if request.inspect_page:
        result = await inspect_page(result, enabled_ai=request.include_ai)
        page = result["page"]
        ai_status = page["ai_status"]
        ai_model = page["ai_model"]
        final_url = page.get("final_url")
        # A known final file/non-HTML URL still needs task-2 pattern and brand checks.
        if page["status"] != "blocked" and final_url and final_url != url:
            final_local = await asyncio.to_thread(
                analyze_url_signals, final_url, brand_texts, request.store_id, compare_brand=False)
    else:
        ai_status = "skipped" if request.include_ai else "disabled"
        ai_model = None
    result = metadata_only_result(result)
    urls = [url, final_local["url_info"]["url"] if final_local else None]
    reports = await verify_official_domains(
        urls, brand_texts, enabled=request.include_ai and result["navigation_allowed"])
    apply_domain_report(local, reports)
    if final_local:
        apply_domain_report(final_local, reports)
    verified_domains = {domain for report in reports.values() if report["status"] == "matched"
                        for domain in report["official_domains"]}
    keywords = apply_domain_keyword_reports(
        check_domain_keywords(urls, brand_words={}, official_domains=verified_domains), reports)
    # Root metadata-v2 contains TLS/age; combined-v2 adds URL/domain/store evidence.
    response = {
        **result,
        "url_analysis": local,
        "final_url_analysis": final_local,
        "score_scope": "tls_domain_age",
        "warning": result["warning"] + " 페이지 AI 분석은 점수와 종합 판정에서 제외됩니다.",
        "ai_status": ai_status,
        "ai_model": ai_model,
        "ai_explanation": fallback_text(result),
        # Printed address next to the QR vs the QR's own (and final) address: catches fake QR stickers.
        "printed_domain_check": compare_printed_domains(
            [url, final_local["url_info"]["url"] if final_local else None], request.printed_domains),
        # Brand words / phishing words inside a non-official domain name (P1-8).
        "domain_keyword_check": keywords,
    }
    # Page AI is reference-only: neither points nor completeness depend on its outcome.
    response["verdict"] = combined_verdict(response, brand_requested=bool(brand_texts))
    # The explanation only rewords the finished result; it never changes score, level or signals.
    explained = await explain_result(response, enabled=request.include_ai and request.include_explanation)
    return {
        **response,
        "ai_explanation": explained["ai_explanation"],
        "explanation": explained["ai_explanation"],
        "explanation_status": explained["ai_status"],
        "explanation_model": explained["ai_model"],
        "explanation_skip_reason": explained.get("skip_reason"),
    }


class BrandOCRRequest(BaseModel):
    # ~3MB image after base64 (4/3 overhead) plus a possible data: prefix.
    image_base64: str = Field(min_length=16, max_length=4_300_000, description="상표가 보이는 사진(JPG/PNG/WebP, 3MB 이하)의 base64")


class BrandCandidate(BaseModel):
    name: str
    registered: bool = Field(description="기존 로컬 OCR 별칭 목록 등록 여부. AI 공식 도메인 검색 가능 여부와 무관합니다.")


class PrintedDomain(BaseModel):
    text: str = Field(description="사진에 인쇄된 그대로의 주소")
    domain: str = Field(description="비교에 쓰는 등록 도메인 (예: starbucks.co.kr)")


class BrandOCRResponse(BaseModel):
    status: Literal["ok", "unavailable", "invalid_image"]
    brands: list[BrandCandidate]
    domains: list[PrintedDomain] = Field(default_factory=list)
    message: str | None = None


@app.post("/api/ocr/brands", response_model=BrandOCRResponse)
async def ocr_brands(request: BrandOCRRequest):
    # Photo goes to the AI gateway once and is not stored, logged or cached.
    return await read_brands(request.image_base64)


app.include_router(url_analysis_router)
app.include_router(ocr_router)
app.include_router(qr_router)
