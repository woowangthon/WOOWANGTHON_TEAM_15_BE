
# URL을 분해하고 형식을 검증하는 파일

import ipaddress
import re
from urllib.parse import urlsplit


def parse_qr_url(qr_text: str) -> dict:

    # 1. URL 길이 확인
    if len(qr_text) > 4096:
        return {"valid": False, "reason": "URL이 너무 깁니다."}

    # 2. 제어문자 확인 (줄바꿈, 탭 등)
    if any(ord(c) < 32 or ord(c) == 127 for c in qr_text):
        return {"valid": False, "reason": "제어문자가 포함된 URL"}

    # 3. URL 양쪽 공백 제거
    url = qr_text.strip()

    if not url or any(c.isspace() for c in url):
        return {"valid": False, "reason": "잘못된 URL 형식"}

    # 4. 백슬래시 검사
    if "\\" in url:
        return {"valid": False, "reason": "백슬래시가 포함된 URL"}

    # 5. 잘못된 퍼센트 인코딩 검사
    if re.search(r"%(?![0-9a-fA-F]{2})", url):
        return {"valid": False, "reason": "잘못된 URL 인코딩"}

    try:
        # 6. URL 구성 요소 분리
        parsed = urlsplit(url)

        # 7. HTTP/HTTPS 주소인지 확인
        if parsed.scheme.lower() not in ("http", "https"):
            return {
                "valid": False,
                "reason": "HTTP/HTTPS URL이 아님"
            }

        # 8. 호스트명 확인
        if not parsed.netloc or not parsed.hostname:
            return {"valid": False, "reason": "도메인이 없음"}

        hostname = parsed.hostname.lower().rstrip(".")

        if not hostname:
            return {"valid": False, "reason": "잘못된 도메인"}

        # 9. 포트 번호 확인
        port = parsed.port

        if port == 0:
            return {"valid": False, "reason": "잘못된 포트 번호"}

        # 10. IP 주소 또는 일반 도메인 확인
        try:
            ipaddress.ip_address(hostname)

        except ValueError:
            # 한글 등 국제화 도메인을 ASCII로 변환
            try:
                hostname = hostname.encode("idna").decode("ascii")
            except UnicodeError:
                return {"valid": False, "reason": "잘못된 도메인"}

            # 도메인 길이 및 구조 검사
            labels = hostname.split(".")

            if len(hostname) > 253 or len(labels) < 2:
                return {"valid": False, "reason": "잘못된 도메인"}

            for label in labels:
                if not re.fullmatch(
                    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?",
                    label
                ):
                    return {
                        "valid": False,
                        "reason": "잘못된 도메인 형식"
                    }

        # 11. 정상 파싱 결과 반환
        return {
            "valid": True,
            "url": url,
            "scheme": parsed.scheme.lower(),
            "hostname": hostname,
            "path": parsed.path,
            "query": parsed.query
        }

    except ValueError:
        return {"valid": False, "reason": "잘못된 URL 형식"}
