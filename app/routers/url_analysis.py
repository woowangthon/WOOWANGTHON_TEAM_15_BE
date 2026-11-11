
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

# URL 분석 기능
from app.services.url_parser import parse_qr_url
from app.services.suspicious_patterns import check_suspicious_patterns
from app.services.brand_domain import compare_brand_domain

# 매장 QR 검증 기능
from app.services.store_qr_verifier import verify_store_qr
from app.services.domain_impersonation import check_domain_impersonation
from app.services.redirect_patterns import check_redirect_patterns

# 매장 검색 및 위험 신호 정리
from app.services.store_registry import search_stores
from app.services.risk_signals import build_risk_signals


# FastAPI 라우터 생성
router = APIRouter()


# QR 분석 요청 데이터
class AnalyzeRequest(BaseModel):
    qr_text: str = Field(min_length=1)
    brand_texts: list[str] = Field(default_factory=list)
    store_id: str | None = None


# QR 분석 응답 데이터
class AnalyzeResponse(BaseModel):
    status: Literal["ok", "invalid_url"]
    url_info: dict[str, Any]
    suspicious_patterns: dict[str, Any]
    brand_domain: dict[str, Any]
    store_qr: dict[str, Any] | None = None
    domain_impersonation: dict[str, Any] | None = None
    redirect_patterns: dict[str, Any] | None = None
    risk_signals: dict[str, Any] | None = None


# QR URL 분석 API
@router.post("/api/url/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest):

    # 1. URL 파싱
    url_info = parse_qr_url(request.qr_text)

    # 2. 의심 URL 패턴 검사
    suspicious = check_suspicious_patterns(request.qr_text)

    # 3. 브랜드 공식 도메인 비교
    brand = compare_brand_domain(
        request.qr_text,
        request.brand_texts
    )

    # 4. 매장 QR 및 위장 도메인 검사
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

    # 5. 외부 리다이렉트 패턴 검사
    redirect = check_redirect_patterns(request.qr_text)

    # 6. 위험 신호 데이터 정리
    risk_signals = build_risk_signals({
        "url_info": url_info,
        "suspicious_patterns": suspicious,
        "brand_domain": brand,
        "store_qr": store_qr,
        "domain_impersonation": domain_impersonation,
        "redirect_patterns": redirect
    })

    # 7. 분석 결과 반환
    return AnalyzeResponse(
        status="ok" if url_info["valid"] else "invalid_url",
        url_info=url_info,
        suspicious_patterns=suspicious,
        brand_domain=brand,
        store_qr=store_qr,
        domain_impersonation=domain_impersonation,
        redirect_patterns=redirect,
        risk_signals=risk_signals
    )


# 매장 이름 검색 API
@router.get("/api/stores/search")
def search_store_api(keyword: str):

    stores = search_stores(keyword)

    return {
        "count": len(stores),
        "stores": stores
    }
