#의심스러운 URL 특징 검사
import ipaddress
from pathlib import PurePosixPath
from urllib.parse import unquote
from app.services.url_parser import parse_qr_url

def check_suspicious_patterns(qr_text: str) -> dict:
    # 1. 기존 URL 파싱 함수 호출
    result = parse_qr_url(qr_text)

    if not result["valid"]:
        return {
            "valid": False,
            "suspicious": None,
            "reasons": [result["reason"]]
        }

    hostname = result["hostname"]
    path = unquote(result["path"]).lower()
    reasons = []

    # 2. IP 주소형 URL 검사
    try:
        ipaddress.ip_address(hostname)
        reasons.append("IP 주소를 직접 사용하는 URL")
    except ValueError:
        pass

    # 3. 단축 URL 검사
    short_domains = {
        "bit.ly", "tinyurl.com", "t.co", "is.gd",
        "cutt.ly", "rebrand.ly"
    }

    if hostname in short_domains:
        reasons.append("단축 URL 사용")

    # 4. 의심스러운 파일 확장자 검사
    risky_extensions = {
        ".apk", ".exe", ".msi", ".bat", ".scr", ".ps1"
    }

    extension = PurePosixPath(path).suffix

    if extension in risky_extensions:
        reasons.append(f"실행 또는 설치 파일 링크: {extension}")

    # 5. @ 기호를 이용한 도메인 혼동 검사
    from urllib.parse import urlsplit
    parsed = urlsplit(result["url"])

    if parsed.username is not None:
        reasons.append("URL에 사용자 정보(@)가 포함됨")

    # 6. 결과 반환
    return {
        "valid": True,
        "suspicious": len(reasons) > 0,
        "reasons": reasons
    }
