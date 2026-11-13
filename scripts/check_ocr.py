"""Run local brand OCR on one JPEG/PNG without starting a server or calling BAZE."""
import argparse
import json
import mimetypes
from pathlib import Path

from app.ocr_models import BrandOCRResponse
from app.services.brand_extraction import BrandRegistryUnavailable
from app.services.ocr import ImageInputError, MAX_IMAGE_BYTES, OCRBusy, OCRUnavailable, recognize_brands


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    try:
        with args.image.open("rb") as source:
            data = source.read(MAX_IMAGE_BYTES + 1)
        result = recognize_brands(data, mimetypes.guess_type(args.image.name)[0])
        payload = BrandOCRResponse.model_validate(result).model_dump()
    except ImageInputError as exc:
        print(json.dumps({"error": exc.detail, "status_code": exc.status_code}, ensure_ascii=True))
        return 1
    except (OSError, OCRUnavailable, OCRBusy, BrandRegistryUnavailable):
        print("OCR check failed. Check the image, dependencies, local models and brand registries.")
        return 1
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
