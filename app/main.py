
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

# URL 분석 라우터 가져오기
from app.routers.url_analysis import router as url_analysis_router


# 팀 공통 FastAPI 서버
app = FastAPI(title="QR Alert API", version="0.1.0")


# 서버 상태 확인 응답
class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


# 기존 서버 상태 확인 API 유지
@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


# URL 분석 및 매장 검색 API 연결
app.include_router(url_analysis_router)
