"""Read QR bytes locally with ZXing; no AI, URL fetching or image persistence."""
import io
import threading
import warnings

import zxingcpp
from PIL import Image, ImageOps, UnidentifiedImageError
from app.brand_ocr import decode_image

MAX_PIXELS = 16_000_000
_slots = threading.BoundedSemaphore(2)


class DecoderBusy(Exception):
    pass


def decode_qr(image_base64):
    if not _slots.acquire(blocking=False):
        raise DecoderBusy()
    try:
        decoded = decode_image(image_base64)
        if decoded is None:
            raise ValueError("3MiB 이하의 JPG/PNG/WebP 사진을 보내 주세요.")
        data, _ = decoded
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data)) as source:
                    if source.format not in {"JPEG", "PNG", "WEBP"} or source.width * source.height > MAX_PIXELS:
                        raise ValueError("지원하지 않는 이미지이거나 사진 해상도가 너무 커요.")
                    # EXIF orientation is materialized; QR decoder handles rotation/inversion itself.
                    with ImageOps.exif_transpose(source) as oriented, oriented.convert("RGB") as image:
                        codes = zxingcpp.read_barcodes(
                            image, formats=zxingcpp.BarcodeFormat.QRCode,
                            try_rotate=True, try_downscale=True, try_invert=True,
                            text_mode=zxingcpp.TextMode.Plain)
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise ValueError("사진 파일을 읽지 못했어요. JPG/PNG 사진을 다시 선택해 주세요.") from exc
        values = list(dict.fromkeys(c.text for c in codes if c.valid and c.text.strip()))
        if any(len(value) > 4096 for value in values):
            raise ValueError("QR 내용이 너무 길어요.")
        if len(values) > 1:
            return {"status": "multiple_qr", "qr_text": None, "decoder": "zxing_cpp", "auto_open": False,
                    "message": "서로 다른 QR이 여러 개 있어요. 검사할 QR 한 개가 나오도록 찍어 주세요."}
        if not values:
            return {"status": "not_found", "qr_text": None, "decoder": "zxing_cpp", "auto_open": False,
                    "message": "휴대폰과 서버 모두 QR을 읽지 못했어요. 원본 QR 이미지나 더 선명한 사진으로 확인해 주세요."}
        return {"status": "ok", "qr_text": values[0], "decoder": "zxing_cpp", "auto_open": False,
                "message": "서버에서 QR을 읽었어요. 주소는 열지 않았어요."}
    finally:
        _slots.release()
