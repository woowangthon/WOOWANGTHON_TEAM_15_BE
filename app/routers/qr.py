from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.qr_decode import decode_qr, DecoderBusy

router = APIRouter()


class QRDecodeRequest(BaseModel):
    image_base64: str = Field(min_length=16, max_length=4_300_000)


class QRDecodeResponse(BaseModel):
    status: Literal["ok", "not_found", "multiple_qr"]
    qr_text: str | None
    decoder: Literal["zxing_cpp"]
    auto_open: Literal[False] = False
    message: str


@router.post("/api/qr/decode", response_model=QRDecodeResponse)
async def decode_photo(request: QRDecodeRequest):
    try:
        return await run_in_threadpool(decode_qr, request.image_base64)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DecoderBusy as exc:
        raise HTTPException(status_code=503, detail="사진 검사 요청이 많아요. 잠시 후 다시 시도해 주세요.") from exc
