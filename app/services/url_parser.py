#URL을 분해하는 파일
from urllib.parse import urlsplit


def parse_qr_url(qr_text: str) -> dict:
    # 1. URL 양쪽 공백 제거
    url = qr_text.strip()

    # 2. URL 내부 공백 및 제어문자 확인
    if not url or any(c.isspace() or ord(c) < 32 for c in url):
        return {"valid": False, "reason": "잘못된 URL 형식"}

    try:
        # 3. URL 구성 요소 분리
        parsed = urlsplit(url)

        # 4. HTTP/HTTPS 주소인지 확인
        if parsed.scheme.lower() not in ("http", "https"):
            return {"valid": False, "reason": "HTTP/HTTPS URL이 아님"}

        # 5. 도메인이 있는지 확인
        if not parsed.hostname:
            return {"valid": False, "reason": "도메인이 없음"}

        # 6. 잘못된 포트 번호 검증
        _ = parsed.port

        # 7. 파싱 결과 반환
        return {
            "valid": True,
            "url": url,
            "scheme": parsed.scheme.lower(),
            "hostname": parsed.hostname.lower(),
            "path": parsed.path,
            "query": parsed.query
        }

    except ValueError:
        return {"valid": False, "reason": "잘못된 URL 형식"}
