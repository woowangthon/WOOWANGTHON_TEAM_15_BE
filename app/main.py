import os
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app import config  # Load the backend .env before reading application settings.
from app.security import analyze_url
from app.ai import fallback_text
from app.models import AnalyzeResponse
from app.page_analysis import inspect_page
from app.routers.url_analysis import router as url_analysis_router

app = FastAPI(title="QR Alert API", version="0.5.0")
origins = [s.strip() for s in os.getenv("CORS_ORIGINS", "").split(",") if s.strip()]
if origins:
    app.add_middleware(CORSMiddleware, allow_origins=origins,
                       allow_methods=["POST", "GET"], allow_headers=["Content-Type"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class AnalyzeRequest(BaseModel):
    qr_text: str = Field(min_length=1, max_length=4096, description="QR에서 읽은 HTTP(S) URL")
    include_ai: bool = Field(default=True, description="AI 설명 생성 여부. false이면 외부 AI 호출 없음")
    inspect_page: bool = Field(default=False, description="대상 사이트에 제한된 GET 요청을 보내 정적 HTML과 AI로 분석합니다.")
    brand_texts: list[str] = Field(max_length=30, description="2번 담당 연동용. 현재 브랜드 비교 미구현")


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse()


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest):
    try:
        result = await analyze_url(request.qr_text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if request.inspect_page:
        result = await inspect_page(result, enabled_ai=request.include_ai)
        page = result["page"]
        ai_status = page["ai_status"]
        ai_model = page["ai_model"]
    else:
        ai_status = "skipped" if request.include_ai else "disabled"
        ai_model = None
    return {**result, "ai_status": ai_status, "ai_model": ai_model,
            "ai_explanation": fallback_text(result)}


# Register URL-pattern and store checks separately from behavior scoring.
app.include_router(url_analysis_router)
