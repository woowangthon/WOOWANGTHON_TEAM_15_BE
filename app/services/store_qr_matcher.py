
# 매장 QR 주소 비교 및 테이블 번호 허용 검사

import re
from urllib.parse import urlsplit, parse_qsl

from app.services.url_parser import parse_qr_url


def match_store_qr_url(
    qr_text: str,
    approved_url: str,
    allowed_query_params: list[str] | None = None
) -> bool:

    # 1. QR 주소 및 등록된 주소 형식 확인
    if not parse_qr_url(qr_text)["valid"]:
        return False

    if not parse_qr_url(approved_url)["valid"]:
        return False

    # 2. 두 URL 분해
    scanned = urlsplit(qr_text.strip())
    approved = urlsplit(approved_url)

    # 3. 사용자 정보 및 프래그먼트 거부
    if scanned.username is not None or approved.username is not None:
        return False

    if scanned.fragment or approved.fragment:
        return False

    # 4. 프로토콜, 호스트 및 포트 비교
    if scanned.scheme.lower() != approved.scheme.lower():
        return False

    if scanned.netloc.lower() != approved.netloc.lower():
        return False

    # 5. URL 경로 비교
    if scanned.path != approved.path:
        return False

    # 6. 쿼리 문자열까지 일치하면 정상
    if scanned.query == approved.query:
        return True

    # 7. 등록된 주소에 고정 쿼리가 있으면 다른 값 거부
    if approved.query:
        return False

    # 8. table 매개변수가 허용되었는지 확인
    allowed = allowed_query_params or []

    if "table" not in allowed:
        return False

    # 9. 쿼리 매개변수 분리
    params = parse_qsl(
        scanned.query,
        keep_blank_values=True
    )

    # table 외 다른 값이 있거나 여러 개면 거부
    if len(params) != 1:
        return False

    key, value = params[0]

    if key != "table":
        return False

    # 10. 테이블 번호는 1~99의 정수만 허용
    if not re.fullmatch(r"[1-9][0-9]?", value):
        return False

    return True
