import os
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app import config  # Load the backend .env before reading application settings.
from app.security import analyze_url
from app.ai import explain_result
from app.models import AnalyzeResponse

app = FastAPI(title="QR Alert API", version="0.3.0")
origins = [s.strip() for s in os.getenv("CORS_ORIGINS", "").split(",") if s.strip()]
if origins:
    app.add_middleware(CORSMiddleware, allow_origins=origins,
                       allow_methods=["POST", "GET"], allow_headers=["Content-Type"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class AnalyzeRequest(BaseModel):
    qr_text: str = Field(min_length=1, max_length=4096, description="QR에서 읽은 HTTP(S) URL")
    include_ai: bool = Field(default=True, description="AI 설명 생성 여부. false이면 외부 AI 호출 없음")
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
    return {**result, **await explain_result(result, enabled=request.include_ai)}
