import asyncio
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.ocr_models import BrandOCRResponse
from app.services.brand_extraction import BrandRegistryUnavailable
from app.services.ocr import ImageInputError, MAX_IMAGE_BYTES, OCRBusy, OCRUnavailable, recognize_brands

router = APIRouter(prefix="/api/ocr", tags=["OCR"])
OCR_TIMEOUT_SECONDS = 30


@router.post("/brands", response_model=BrandOCRResponse)
async def extract_brands(image: Annotated[UploadFile, File(description="상표명이 보이는 JPEG/PNG 사진. 최대 5MiB")]):
    try:
        content = await image.read(MAX_IMAGE_BYTES + 1)
        return await asyncio.wait_for(
            asyncio.to_thread(recognize_brands, content, image.content_type), OCR_TIMEOUT_SECONDS)
    except ImageInputError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    except OCRBusy:
        raise HTTPException(status_code=503, detail="문자인식이 진행 중입니다. 잠시 후 다시 시도해주세요.",
                            headers={"Retry-After": "3"}) from None
    except (OCRUnavailable, BrandRegistryUnavailable):
        raise HTTPException(status_code=503, detail="문자인식 서비스를 준비하지 못했습니다. 잠시 후 다시 시도해주세요.") from None
    except TimeoutError:
        # The CPU thread retains its lock until finished; further requests get busy.
        raise HTTPException(status_code=504, detail="문자인식 시간이 초과되었습니다. 글자가 크게 보이는 사진으로 다시 시도해주세요.") from None
    finally:
        await image.close()
