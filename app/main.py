from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field


app = FastAPI(title="QR Alert API", version="0.1.0")


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class AnalyzeRequest(BaseModel):
    qr_text: str = Field(min_length=1, description="QR에서 읽은 원문 텍스트")
    brand_texts: list[str] = Field(description="비교할 브랜드 텍스트 목록")


class AnalyzeResponse(BaseModel):
    status: Literal["not_implemented"] = "not_implemented"
    message: str = "분석 기능은 아직 구현되지 않았습니다."


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    # 요청 형식만 검증합니다. QR 주소를 열거나 외부 요청을 보내지 않습니다.
    return AnalyzeResponse()
