
# 등록된 매장을 이름으로 검색하는 기능

import json
from pathlib import Path


def search_stores(keyword: str) -> list[dict]:

    # 1. 검색어 정리
    keyword = keyword.strip().casefold()

    if not keyword:
        return []

    # 2. 매장 정보 파일 경로
    db_path = (
        Path(__file__).resolve().parent.parent
        / "data" / "store_qr_registry.json"
    )

    # 3. 저장된 매장 정보 불러오기
    with open(db_path, "r", encoding="utf-8") as f:
        stores = json.load(f)

    results = []

    # 4. 매장 이름 검색
    for store_id, store in stores.items():

        store_name = store.get("store_name", "")

        if keyword in store_name.casefold():
            results.append({
                "store_id": store_id,
                "store_name": store_name,
                "qr_type": store.get("qr_type", "unknown"),
                "verification_status": store.get(
                    "verification_status", "unverified"
                )
            })

    # 5. 검색 결과 반환
    return results
