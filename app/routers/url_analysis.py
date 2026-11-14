import asyncio

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.store_registry import search_stores
from app.services.url_analysis import analyze_url_signals
from app.services.url_resolution import resolve_url
from app.domain_ai import verify_official_domains, apply_domain_report
from app.url_models import ExpandedURLAnalysisResponse

router = APIRouter()


class AnalyzeRequest(BaseModel):
    qr_text: str = Field(min_length=1, max_length=4096)
    brand_texts: list[str] = Field(default_factory=list, max_length=30)
    store_id: str | None = Field(default=None, min_length=1, max_length=128)
    include_ai: bool = Field(default=False, description="BAZE 웹 검색으로 공식 도메인 판정. false이면 확인 불가로 반환하며 고정 DB를 대신 사용하지 않습니다.")
    resolve_redirects: bool = Field(default=False, description="서버가 HTTP 이동 주소를 확인해 최종 URL도 검사합니다. 본문·AI 분석은 하지 않습니다.")


@router.post("/api/url/analyze", response_model=ExpandedURLAnalysisResponse, response_model_exclude_unset=True)
async def analyze(request: AnalyzeRequest):
    original = await asyncio.to_thread(
        analyze_url_signals, request.qr_text, request.brand_texts, request.store_id, compare_brand=False)
    if not original["url_info"]["valid"]:
        return original
    resolution = await resolve_url(request.qr_text) if request.resolve_redirects else None
    final = resolution.get("final_url") if resolution else None
    final_analysis = None
    if final and resolution["status"] in {"ok", "not_applicable"} and final != original["url_info"]["url"]:
        final_analysis = await asyncio.to_thread(
            analyze_url_signals, final, request.brand_texts, request.store_id, compare_brand=False)
    # A blocked redirect prevents external AI disclosure of the entire scan.
    reports = await verify_official_domains(
        [original["url_info"]["url"], final_analysis["url_info"]["url"] if final_analysis else None],
        request.brand_texts, enabled=request.include_ai and (not resolution or resolution["status"] != "blocked"))
    apply_domain_report(original, reports)
    if final_analysis:
        apply_domain_report(final_analysis, reports)
    if resolution is None:
        return original
    return {**original, "url_resolution": resolution, "final_url_analysis": final_analysis}


@router.get("/api/stores/search")
def search_store_api(keyword: str):
    stores = search_stores(keyword)
    return {"count": len(stores), "stores": stores}
