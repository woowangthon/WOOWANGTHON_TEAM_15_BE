
from typing import Any, Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field

# 1. URL 분석 기능
from app.services.url_parser import parse_qr_url
from app.services.suspicious_patterns import check_suspicious_patterns
from app.services.brand_domain import compare_brand_domain
# 2. 매장 QR 검증 기능
from app.services.store_qr_verifier import verify_store_qr
# 3. 위장 도메인 탐지 기능
from app.services.domain_impersonation import check_domain_impersonation
from app.services.redirect_patterns import check_redirect_patterns


app = FastAPI(title="QR Guard URL Analysis API")


# 요청 데이터 형식
class AnalyzeRequest(BaseModel):
    qr_text: str = Field(min_length=1)
    brand_texts: list[str] = Field(default_factory=list)
    store_id: str | None = None


# 응답 데이터 형식
class AnalyzeResponse(BaseModel):
    status: Literal["ok", "invalid_url"]
    url_info: dict[str, Any]
    suspicious_patterns: dict[str, Any]
    brand_domain: dict[str, Any]
    store_qr: dict[str, Any] | None = None
    domain_impersonation: dict[str, Any] | None = None
    redirect_patterns: dict[str, Any] | None = None


# URL 분석 API
@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest):

    # 1. URL 파싱
    url_info = parse_qr_url(request.qr_text)

    # 2. 의심 패턴 검사
    suspicious = check_suspicious_patterns(request.qr_text)

    # 3. 브랜드 공식 도메인 비교
    brand = compare_brand_domain(
        request.qr_text,
        request.brand_texts
    )

    # 4. 매장 QR 검증 및 위장 도메인 검사
    store_qr = None
    domain_impersonation = None

    if request.store_id:
        store_qr = verify_store_qr(
            request.qr_text,
            request.store_id
        )

        domain_impersonation = check_domain_impersonation(
            request.qr_text,
            request.store_id
        )

    redirect = check_redirect_patterns(request.qr_text)

    # 5. 모든 분석 결과 반환
    return AnalyzeResponse(
        status="ok" if url_info["valid"] else "invalid_url",
        url_info=url_info,
        suspicious_patterns=suspicious,
        brand_domain=brand,
        store_qr=store_qr,
        domain_impersonation=domain_impersonation,
        redirect_patterns=redirect     
    )
