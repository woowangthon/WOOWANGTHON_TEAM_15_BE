"""Prepare local ko/en OCR models; normal image API requests never download models."""
import argparse
from app.config import ocr_settings
from app.services.ocr import OCRUnavailable, create_reader


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-models", action="store_true", help="Download missing OCR weights into OCR_MODEL_DIR")
    args = parser.parse_args()
    try:
        create_reader(download_enabled=args.download_models)
    except (OCRUnavailable, ValueError):
        print("OCR is not ready. Install requirements-ocr.txt and run with --download-models once.")
        return 1
    print("OCR ready: ko/en, CPU, models=" + str(ocr_settings()["model_dir"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
