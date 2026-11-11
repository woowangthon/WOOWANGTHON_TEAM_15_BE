#브랜드와 도메인을 비교하는 파일
#첫번째 인자: QR에서 추출한 URL
#두번째 인자: OCR로 인식한 브랜드명 목록
import json
from pathlib import Path
from app.services.url_parser import parse_qr_url


def compare_brand_domain(qr_text: str, brand_texts: list[str]) -> dict:
    # 1. QR URL 분석
    parsed = parse_qr_url(qr_text)

    if not parsed["valid"]:
        return {
            "status": "invalid_url",
            "reason": parsed["reason"]
        }

    hostname = parsed["hostname"].rstrip(".").lower()

    # 2. 공식 도메인 DB 불러오기
    db_path = (
        Path(__file__).resolve().parent.parent
        / "data" / "official_domains.json"
    )

    with open(db_path, "r", encoding="utf-8") as f:
        official_domains = json.load(f)

    # 3. OCR에서 추출한 브랜드명 정리
    recognized = {
        brand.strip().casefold()
        for brand in brand_texts
        if brand.strip()
    }

    # 4. DB에 등록된 브랜드와 비교
    for brand, domains in official_domains.items():
        if brand.casefold() not in recognized:
            continue

        for domain in domains:
            domain = domain.lower().rstrip(".")

            # 정확히 일치하거나 공식 도메인의 하위 도메인인지 검사
            if hostname == domain or hostname.endswith("." + domain):
                return {
                    "status": "matched",
                    "brand": brand,
                    "reason": "등록된 공식 도메인과 일치"
                }

        return {
            "status": "mismatched",
            "brand": brand,
            "reason": "등록된 공식 도메인과 불일치"
        }

    # 5. 등록된 브랜드를 찾지 못한 경우
    return {
        "status": "unknown",
        "reason": "공식 도메인 확인 불가"
    }
