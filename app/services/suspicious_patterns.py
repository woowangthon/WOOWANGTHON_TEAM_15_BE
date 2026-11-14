
# 의심스러운 URL 특징 검사

import ipaddress
from pathlib import PurePosixPath
from urllib.parse import unquote, parse_qsl, urlsplit

from app.services.url_parser import parse_qr_url


# 여러 번 인코딩된 문자열을 최대 3번 디코딩
def decode_repeatedly(value: str, max_rounds: int = 3) -> str:
    for _ in range(max_rounds):
        decoded = unquote(value)

        # 더 이상 디코딩할 문자가 없으면 종료
        if decoded == value:
            break

        value = decoded

    return value


def check_suspicious_patterns(qr_text: str) -> dict:
    # 1. 기존 URL 파싱 함수 호출
    result = parse_qr_url(qr_text)

    if not result["valid"]:
        return {
            "valid": False,
            "suspicious": None,
            "codes": [],
            "reasons": [result["reason"]]
        }

    hostname = result["hostname"]
    path = decode_repeatedly(result["path"]).lower()
    reasons = []
    codes = []

    # 2. IP 주소형 URL 검사
    try:
        ipaddress.ip_address(hostname)
        codes.append("IP_LITERAL")
        reasons.append("IP 주소를 직접 사용하는 URL")
    except ValueError:
        pass

    # 3. 단축 URL 검사
    short_domains = {
        "bit.ly", "tinyurl.com", "t.co", "is.gd",
        "cutt.ly", "rebrand.ly", "m.site.naver.com", "naver.me"
    }

    if hostname in short_domains:
        codes.append("SHORT_URL")
        reasons.append("단축 URL 사용")

    # 4. 의심스러운 파일 확장자 검사
    risky_extensions = {
        ".apk", ".exe", ".msi", ".bat", ".scr", ".ps1"
    }

    extension = PurePosixPath(path).suffix

    if extension in risky_extensions:
        codes.append("EXECUTABLE_LINK")
        reasons.append(
            f"실행 또는 설치 파일 링크: {extension}"
        )

    # 5. 쿼리 문자열에 포함된 위험 파일명 검사
    query_params = parse_qsl(
        result["query"],
        keep_blank_values=True
    )

    for key, value in query_params:
        filename = decode_repeatedly(value).lower()
        extension = PurePosixPath(filename).suffix

        if extension in risky_extensions:
            codes.append("EXECUTABLE_QUERY")
            reasons.append(
                f"쿼리 매개변수에 실행 또는 설치 파일명 포함: {extension}"
            )
            break

    # 6. @ 기호를 이용한 도메인 혼동 검사
    parsed = urlsplit(result["url"])

    if parsed.username is not None:
        codes.append("USERINFO_IN_URL")
        reasons.append("URL에 사용자 정보(@)가 포함됨")

    # 7. 결과 반환
    return {
        "valid": True,
        "suspicious": len(reasons) > 0,
        "codes": codes,
        "reasons": reasons
    }
