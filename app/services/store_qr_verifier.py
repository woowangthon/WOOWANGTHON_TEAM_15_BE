
# 매장 QR 주소 및 검증 상태 확인

import json
from pathlib import Path

from app.services.url_parser import parse_qr_url
from app.services.store_qr_matcher import match_store_qr_url

def verify_store_qr(qr_text: str, store_id: str) -> dict:

    # 1. QR URL 형식 확인
    parsed = parse_qr_url(qr_text)

    if not parsed["valid"]:
        return {
            "status": "invalid_url",
            "reason": parsed["reason"]
        }

    # 2. 매장 QR 데이터 불러오기
    db_path = (
        Path(__file__).resolve().parent.parent
        / "data" / "store_qr_registry.json"
    )

    with open(db_path, "r", encoding="utf-8") as f:
        stores = json.load(f)

    # 3. 매장 ID로 검색
    store = stores.get(store_id)

    if store is None:
        return {
            "status": "unknown",
            "is_store_verified": False,
            "reason": "등록되지 않은 매장입니다."
        }

    # 4. 매장 정보 검증 상태 확인
    verification_status = store.get(
        "verification_status", "unverified"
    )

    is_store_verified = verification_status == "verified"

    # 5. 승인된 QR 주소 가져오기
    approved_urls = store.get("approved_urls", [])

    if not approved_urls:
        return {
            "status": "unknown",
            "store_name": store["store_name"],
            "is_store_verified": is_store_verified,
            "reason": "등록된 QR 주소가 없습니다."
        }

    # 6. 매장에 허용된 쿼리 매개변수 가져오기
    allowed_query_params = store.get(
        "allowed_query_params", []
    )

    # 7. 등록된 QR 주소들과 비교
    is_matched = any(
        match_store_qr_url(
            qr_text,
            approved_url,
            allowed_query_params
        )
        for approved_url in approved_urls
    )


    # 8. QR 주소 일치 여부와 매장 검증 상태에 따른 설명
    if not is_store_verified:
        if is_matched:
            reason = (
                "등록된 QR 주소와 일치하지만, "
                "실제 매장의 승인 여부는 확인되지 않았습니다."
            )
        else:
            reason = (
                "등록된 QR 주소와 다릅니다. "
                "단, 실제 매장의 승인 정보가 없어 진위는 확인할 수 없습니다."
            )

    elif is_matched:
        reason = "검증된 매장 정보에 등록된 QR 주소와 일치합니다."

    else:
        reason = "검증된 매장 정보에 등록된 QR 주소와 다릅니다."


    # 9. 검사 결과 반환
    return {
        "status": "matched" if is_matched else "mismatched",
        "store_name": store["store_name"],
        "verification_status": verification_status,
        "is_store_verified": is_store_verified,
        "reason": reason
    }
