import asyncio

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.store_registry import search_stores
from app.services.url_analysis import analyze_url_signals
from app.services.url_resolution import resolve_url
from app.url_models import ExpandedURLAnalysisResponse

router = APIRouter()


class AnalyzeRequest(BaseModel):
    qr_text: str = Field(min_length=1, max_length=4096)
    brand_texts: list[str] = Field(default_factory=list, max_length=30)
    store_id: str | None = Field(default=None, min_length=1, max_length=128)
    resolve_redirects: bool = Field(default=False, description="서버가 HTTP 이동 주소를 확인해 최종 URL도 검사합니다. 본문·AI 분석은 하지 않습니다.")


@router.post("/api/url/analyze", response_model=ExpandedURLAnalysisResponse, response_model_exclude_unset=True)
async def analyze(request: AnalyzeRequest):
    original = await asyncio.to_thread(analyze_url_signals, request.qr_text, request.brand_texts, request.store_id)
    # Preserve the existing local-only response and no-network behavior unless explicitly enabled.
    if not request.resolve_redirects or not original["url_info"]["valid"]:
        return original
    resolution = await resolve_url(request.qr_text)
    final = resolution.get("final_url")
    final_analysis = None
    # File destinations are still useful task-2 evidence, even when the policy refuses to fetch them.
    if final and resolution["status"] in {"ok", "not_applicable"} and final != original["url_info"]["url"]:
        final_analysis = await asyncio.to_thread(analyze_url_signals, final, request.brand_texts, request.store_id)
    return {**original, "url_resolution": resolution, "final_url_analysis": final_analysis}


@router.get("/api/stores/search")
def search_store_api(keyword: str):
    stores = search_stores(keyword)
    return {"count": len(stores), "stores": stores}
