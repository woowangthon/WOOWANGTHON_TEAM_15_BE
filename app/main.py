import asyncio
import os
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app import config  # Load backend-local .env before reading settings.
from app.security import analyze_url, parse_url
from app.ai import explain_result, fallback_text
from app.brand_ocr import read_brands
from app.models import AnalyzeResponse
from app.page_analysis import inspect_page
from app.routers.url_analysis import router as url_analysis_router
from app.services.brand_alias import expand_brand_texts
from app.services.domain_keywords import check_domain_keywords
from app.services.printed_domain import compare_printed_domains
from app.services.url_analysis import analyze_url_signals
from app.verdict import combined_verdict
from app.routers.ocr import router as ocr_router
from app.middleware.ocr_upload import OCRUploadLimitMiddleware

app = FastAPI(title="QR Alert API", version="0.7.0")
app.add_middleware(OCRUploadLimitMiddleware)
origins = [s.strip() for s in os.getenv("CORS_ORIGINS", "").split(",") if s.strip()]
if origins:
    app.add_middleware(CORSMiddleware, allow_origins=origins,
                       allow_methods=["POST", "GET"], allow_headers=["Content-Type"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class AnalyzeRequest(BaseModel):
    qr_text: str = Field(min_length=1, max_length=4096, description="QR에서 읽은 HTTP(S) URL")
    include_ai: bool = Field(default=True, description="페이지 AI 행동 분석 사용 여부. false이면 외부 AI 호출 없음")
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
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # "네이버 웹툰" also counts as "네이버" for the official-domain comparison (exact-name DB).
    brand_texts = expand_brand_texts(request.brand_texts)
    local = await asyncio.to_thread(analyze_url_signals, url, brand_texts, request.store_id)
    if not local["url_info"]["valid"]:
        raise HTTPException(status_code=422, detail=local["url_info"].get("reason", "잘못된 URL입니다."))
    result = await analyze_url(url)
    final_local = None
    if request.inspect_page:
        result = await inspect_page(result, enabled_ai=request.include_ai)
        page = result["page"]
        ai_status = page["ai_status"]
        ai_model = page["ai_model"]
        final_url = page.get("final_url")
        if page["status"] == "ok" and final_url and final_url != url:
            final_local = await asyncio.to_thread(
                analyze_url_signals, final_url, brand_texts, request.store_id)
    else:
        ai_status = "skipped" if request.include_ai else "disabled"
        ai_model = None
    # behavior-v1 stays reproducible: task-2 observations do not add/subtract points.
    response = {
        **result,
        "url_analysis": local,
        "final_url_analysis": final_local,
        "score_scope": "ai_behavior_tls_domain_age",
        "warning": result["warning"] + " URL·브랜드·매장 검사 신호는 behavior-v1 점수에 포함되지 않습니다.",
        "ai_status": ai_status,
        "ai_model": ai_model,
        "ai_explanation": fallback_text(result),
        # Printed address next to the QR vs the QR's own (and final) address: catches fake QR stickers.
        "printed_domain_check": compare_printed_domains(
            [url, final_local["url_info"]["url"] if final_local else None], request.printed_domains),
        # Brand words / phishing words inside a non-official domain name (P1-8).
        "domain_keyword_check": check_domain_keywords([url, final_local["url_info"]["url"] if final_local else None]),
    }
    # Overall verdict (combined-v1) adds URL/brand/store signals on top of behavior-v1.
    response["verdict"] = combined_verdict(response)
    # The explanation only rewords the finished result; it never changes score, level or signals.
    explained = await explain_result(response, enabled=request.include_ai and request.include_explanation)
    return {
        **response,
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
    registered: bool = Field(description="공식 도메인 DB에 있는 상표명이면 true (비교 가능)")


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
