"""OCR results are candidates for user confirmation, never proof of brand ownership."""
from typing import Literal
from pydantic import BaseModel, Field


class OCRTextBlock(BaseModel):
    text: str = Field(max_length=200)
    confidence: float = Field(ge=0, le=1)
    bounding_box: list[tuple[int, int]] = Field(min_length=4, max_length=4)


class BrandCandidate(BaseModel):
    brand: str
    matched_text: str
    ocr_confidence: float = Field(ge=0, le=1)


class BrandOCRResponse(BaseModel):
    ocr_status: Literal["ok", "no_text", "no_brand", "low_confidence", "ambiguous"]
    texts: list[OCRTextBlock] = Field(max_length=50)
    brand_candidates: list[BrandCandidate] = Field(max_length=10)
    brand_texts: list[str] = Field(max_length=1)
    requires_confirmation: Literal[True] = True
    processed_width: int
    processed_height: int
    truncated: bool = False
    min_confidence: float
    note: str = "OCR 신뢰도는 글자 인식 신뢰도입니다. 브랜드와 사이트의 진위를 보증하지 않습니다. 후보를 확인한 뒤 분석에 사용하세요."
