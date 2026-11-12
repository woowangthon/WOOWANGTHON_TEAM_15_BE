from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.store_registry import search_stores
from app.services.url_analysis import analyze_url_signals
from app.url_models import URLAnalysisResponse

router = APIRouter()


class AnalyzeRequest(BaseModel):
    qr_text: str = Field(min_length=1, max_length=4096)
    brand_texts: list[str] = Field(default_factory=list, max_length=30)
    store_id: str | None = Field(default=None, min_length=1, max_length=128)


@router.post("/api/url/analyze", response_model=URLAnalysisResponse)
def analyze(request: AnalyzeRequest):
    return analyze_url_signals(request.qr_text, request.brand_texts, request.store_id)


@router.get("/api/stores/search")
def search_store_api(keyword: str):
    stores = search_stores(keyword)
    return {"count": len(stores), "stores": stores}
