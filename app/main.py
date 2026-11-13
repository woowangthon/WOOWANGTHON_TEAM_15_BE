import asyncio
import os
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app import config  # Load backend-local .env before reading settings.
from app.security import analyze_url, parse_url
from app.ai import explain_result, fallback_text
from app.models import AnalyzeResponse
from app.page_analysis import inspect_page
from app.routers.url_analysis import router as url_analysis_router
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
    local = await asyncio.to_thread(analyze_url_signals, url, request.brand_texts, request.store_id)
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
                analyze_url_signals, final_url, request.brand_texts, request.store_id)
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


app.include_router(url_analysis_router)
app.include_router(ocr_router)
