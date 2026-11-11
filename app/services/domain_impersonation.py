#공식 도메인과 비슷하게 만들어 사용자를 속이려는 흔적이 있는지 검사
import json
from pathlib import Path
from difflib import SequenceMatcher

from app.services.url_parser import parse_qr_url


def check_domain_impersonation(qr_text: str, store_id: str) -> dict:

    # 1. QR URL 파싱
    parsed = parse_qr_url(qr_text)

    if not parsed["valid"]:
        return {
            "status": "invalid_url",
            "reason": parsed["reason"]
        }

    hostname = parsed["hostname"].lower().rstrip(".")

    # 2. 매장 QR 데이터 불러오기
    db_path = (
        Path(__file__).resolve().parent.parent
        / "data" / "store_qr_registry.json"
    )

    with open(db_path, "r", encoding="utf-8") as f:
        stores = json.load(f)

    # 3. 매장 정보 확인
    store = stores.get(store_id)

    if store is None:
        return {
            "status": "unknown",
            "reason": "등록되지 않은 매장입니다."
        }

    approved_urls = store.get("approved_urls", [])

    # 4. 등록된 QR 주소에서 호스트명 추출
    approved_hosts = set()

    for url in approved_urls:
        official = parse_qr_url(url)

        if official["valid"]:
            approved_hosts.add(
                official["hostname"].lower().rstrip(".")
            )

    if not approved_hosts:
        return {
            "status": "unknown",
            "reason": "비교할 승인된 도메인이 없습니다."
        }

    # 5. 등록된 호스트와 정확하게 일치하는지 확인
    if hostname in approved_hosts:
        return {
            "status": "host_matched",
            "reason": "등록된 매장 호스트명과 일치합니다."
        }

    # 6. 위장 도메인 패턴 검사
    for official_host in approved_hosts:

        # 공식 호스트명을 다른 도메인에 포함시킨 경우
        if official_host in hostname:
            return {
                "status": "impersonation_suspected",
                "reason": "공식 호스트명을 포함한 다른 도메인입니다."
            }

        # 공식 호스트명과 문자열이 매우 비슷한 경우
        similarity = SequenceMatcher(
            None, hostname, official_host
        ).ratio()

        if similarity >= 0.88:
            return {
                "status": "impersonation_suspected",
                "reason": "공식 호스트명과 매우 유사한 도메인입니다."
            }

    # 7. 그 외 등록되지 않은 도메인
    return {
        "status": "other_domain",
        "reason": "등록된 매장 도메인과 다릅니다."
    }
