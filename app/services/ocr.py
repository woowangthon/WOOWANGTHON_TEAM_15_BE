"""Bounded JPEG/PNG decoding and one reusable CPU EasyOCR reader per process."""
import io
import math
import threading
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import ocr_settings
from app.services.brand_extraction import extract_brand_candidates

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
MAX_IMAGE_EDGE = 1600
MAX_TEXT_BLOCKS = 50
_pipeline_lock = threading.Lock()
_reader = None
_reader_path = None


class ImageInputError(ValueError):
    def __init__(self, detail, status_code=400):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class OCRUnavailable(Exception):
    pass


class OCRBusy(Exception):
    pass


def prepare_image(data, content_type):
    if not data:
        raise ImageInputError("이미지 파일이 비어 있습니다.")
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageInputError("이미지는 5MiB 이하여야 합니다.", 413)
    expected = {"image/jpeg": "JPEG", "image/png": "PNG"}.get((content_type or "").split(";", 1)[0].strip().lower())
    if not expected:
        raise ImageInputError("JPEG 또는 PNG 이미지만 지원합니다.", 415)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as probe:
                if probe.format != expected:
                    raise ImageInputError("파일 내용과 이미지 형식이 일치하지 않습니다.", 415)
                if probe.width * probe.height > MAX_IMAGE_PIXELS:
                    raise ImageInputError("이미지 해상도는 1,600만 화소 이하여야 합니다.", 413)
                if getattr(probe, "n_frames", 1) != 1:
                    raise ImageInputError("움직이는 이미지 대신 한 장의 사진을 보내주세요.", 415)
                probe.verify()
            with Image.open(io.BytesIO(data)) as source:
                oriented = ImageOps.exif_transpose(source)
                rgba = oriented.convert("RGBA")
                image = Image.new("RGB", rgba.size, "white")
                image.paste(rgba, mask=rgba.getchannel("A"))
                rgba.close()
                if oriented is not source:
                    oriented.close()
                image.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE), Image.Resampling.LANCZOS)
                return image
    except ImageInputError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ImageInputError("이미지 해상도가 너무 큽니다.", 413) from None
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise ImageInputError("이미지 파일을 읽지 못했습니다. 다른 사진을 선택해주세요.") from None


def create_reader(download_enabled=False):
    settings = ocr_settings()
    model_dir = settings["model_dir"]
    if not download_enabled and not model_dir.is_dir():
        raise OCRUnavailable("OCR 모델이 준비되지 않았습니다.")
    try:
        import torch
        import easyocr
        torch.set_num_threads(2)
        return easyocr.Reader(["ko", "en"], gpu=False, model_storage_directory=str(model_dir),
                              user_network_directory=str(model_dir / "user_network"),
                              download_enabled=download_enabled, verbose=False)
    except (ImportError, OSError, RuntimeError, ValueError, EOFError):
        raise OCRUnavailable("OCR 엔진 또는 모델을 준비하지 못했습니다.") from None


def get_reader():
    global _reader, _reader_path
    path = ocr_settings()["model_dir"]
    if _reader is None or _reader_path != path:
        _reader = create_reader(download_enabled=False)
        _reader_path = path
    return _reader


def normalize_blocks(raw, width, height):
    blocks = []
    for item in raw:
        if len(blocks) >= MAX_TEXT_BLOCKS:
            break
        try:
            box, text, confidence = item
            confidence = float(confidence)
            if not isinstance(text, str) or not text.strip() or not math.isfinite(confidence) or not 0 <= confidence <= 1:
                continue
            if len(box) != 4:
                continue
            points = []
            for x, y in box:
                if not math.isfinite(float(x)) or not math.isfinite(float(y)):
                    raise ValueError("Invalid point")
                points.append((max(0, min(width, round(float(x)))), max(0, min(height, round(float(y))))))
            blocks.append({"text": text.strip()[:200], "confidence": confidence, "bounding_box": points})
        except (TypeError, ValueError, OverflowError):
            continue
    return blocks


def recognize_brands(data, content_type):
    if not _pipeline_lock.acquire(blocking=False):
        raise OCRBusy("다른 이미지를 인식하고 있습니다.")
    image = None
    try:
        image = prepare_image(data, content_type)
        try:
            settings = ocr_settings()
        except (ValueError, OSError):
            raise OCRUnavailable("OCR 설정을 읽지 못했습니다.") from None
        try:
            import numpy as np
            raw = get_reader().readtext(np.asarray(image), detail=1, paragraph=False, workers=0,
                                        batch_size=1, canvas_size=1600)
        except ImportError:
            raise OCRUnavailable("OCR 엔진이 준비되지 않았습니다.") from None
        except (RuntimeError, OSError, ValueError):
            raise OCRUnavailable("이미지 문자를 인식하지 못했습니다.") from None
        if not isinstance(raw, (list, tuple)):
            raise OCRUnavailable("OCR 결과를 해석하지 못했습니다.")
        blocks = normalize_blocks(raw, *image.size)
        candidates = extract_brand_candidates(blocks)
        accepted = [item for item in candidates if item["ocr_confidence"] >= settings["min_confidence"]]
        if not blocks:
            status = "no_text"
        elif len(accepted) > 1:
            status = "ambiguous"
        elif accepted:
            status = "ok"
        elif candidates or max(block["confidence"] for block in blocks) < settings["min_confidence"]:
            status = "low_confidence"
        else:
            status = "no_brand"
        return {"ocr_status": status, "texts": blocks, "brand_candidates": candidates,
                "brand_texts": [accepted[0]["brand"]] if len(accepted) == 1 else [],
                "requires_confirmation": True, "processed_width": image.width,
                "processed_height": image.height, "truncated": len(raw) > MAX_TEXT_BLOCKS,
                "min_confidence": settings["min_confidence"]}
    finally:
        if image is not None:
            image.close()
        _pipeline_lock.release()
