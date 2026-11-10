#매장의 QR 주소와 DB에 저장된 승인된 QR 주소가 일치하는지 검사
import json
from pathlib import Path

from app.services.url_parser import parse_qr_url


def verify_store_qr(qr_text: str, store_id: str) -> dict:

    # 1. QR URL 형식 확인
    parsed = parse_qr_url(qr_text)

    if not parsed["valid"]:
        return {
            "status": "invalid_url",
            "reason": parsed["reason"]
        }

    # 2. 매장 QR 데이터베이스 경로
    db_path = (
        Path(__file__).resolve().parent.parent
        / "data" / "store_qr_registry.json"
    )

    # 3. 저장된 매장 정보 불러오기
    with open(db_path, "r", encoding="utf-8") as f:
        stores = json.load(f)

    # 4. 매장 ID로 매장 검색
    store = stores.get(store_id)

    if store is None:
        return {
            "status": "unknown",
            "reason": "등록되지 않은 매장입니다."
        }

    # 5. 승인된 QR 주소 가져오기
    approved_urls = store.get("approved_urls", [])

    if not approved_urls:
        return {
            "status": "unknown",
            "reason": "등록된 QR 주소가 없습니다."
        }

    # 6. QR 주소를 등록된 주소와 비교
    if qr_text.strip() in approved_urls:
        return {
            "status": "matched",
            "store_name": store["store_name"],
            "reason": "등록된 매장 QR 주소와 일치합니다."
        }

    # 7. 주소가 다르면 불일치 반환
    return {
        "status": "mismatched",
        "store_name": store["store_name"],
        "reason": "등록된 매장 QR 주소와 다릅니다."
    }
