#QR URL의 외부 사이트 이동 유도 패턴 검사

# URL에 포함된 외부 사이트 이동 유도 패턴 검사

from urllib.parse import parse_qsl

from app.services.url_parser import parse_qr_url
from app.services.suspicious_patterns import decode_repeatedly


def check_redirect_patterns(qr_text: str) -> dict:

    # 1. URL 형식 검사
    result = parse_qr_url(qr_text)

    if not result["valid"]:
        return {
            "valid": False,
            "suspicious": None,
            "reasons": [result["reason"]]
        }

    hostname = result["hostname"]
    reasons = []

    # 2. 외부 이동에 사용될 수 있는 매개변수 이름
    redirect_keys = {
        "url",
        "redirect",
        "redirect_url",
        "next",
        "target",
        "destination",
        "return_url"
    }

    # 3. URL 쿼리 문자열 분리
    query_params = parse_qsl(
        result["query"],
        keep_blank_values=True
    )

    # 4. 이동 관련 매개변수 확인
    for key, value in query_params:

        if key.lower() not in redirect_keys:
            continue

        # 인코딩된 주소 복원
        target_url = decode_repeatedly(value)

        # 포함된 URL 분석
        target = parse_qr_url(target_url)

        if not target["valid"]:
            continue

        # 5. 원래 호스트명과 이동 대상 호스트명 비교
        if target["hostname"] != hostname:
            reasons.append(
                f"외부 사이트 이동 가능성: {target['hostname']}"
            )

    # 6. 검사 결과 반환
    return {
        "valid": True,
        "suspicious": len(reasons) > 0,
        "reasons": reasons
    }
