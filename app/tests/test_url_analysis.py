
import unittest

from app.services.url_parser import parse_qr_url
from app.services.suspicious_patterns import check_suspicious_patterns
from app.services.brand_domain import compare_brand_domain


class TestURLAnalysis(unittest.TestCase):

    # 1. 정상 URL 파싱
    def test_normal_url(self):
        result = parse_qr_url("https://example.com/login")

        self.assertTrue(result["valid"])
        self.assertEqual(result["hostname"], "example.com")
        self.assertEqual(result["path"], "/login")

    # 2. 잘못된 URL
    def test_invalid_url(self):
        result = parse_qr_url("not-a-url")

        self.assertFalse(result["valid"])

    # 3. 단축 URL 탐지
    def test_short_url(self):
        result = check_suspicious_patterns(
            "https://bit.ly/abc123"
        )

        self.assertTrue(result["suspicious"])

    # 4. IP 주소형 URL 탐지
    def test_ip_url(self):
        result = check_suspicious_patterns(
            "http://192.168.0.1/login"
        )

        self.assertTrue(result["suspicious"])

    # 5. APK 파일 탐지
    def test_apk_url(self):
        result = check_suspicious_patterns(
            "https://example.com/app.apk"
        )

        self.assertTrue(result["suspicious"])

    # 6. EXE 파일 탐지
    def test_exe_url(self):
        result = check_suspicious_patterns(
            "https://example.com/setup.exe"
        )

        self.assertTrue(result["suspicious"])

    # 7. @ 기호를 이용한 도메인 혼동
    def test_at_symbol(self):
        result = check_suspicious_patterns(
            "https://example.com@evil.example/login"
        )

        self.assertTrue(result["suspicious"])

    # 8. 공식 도메인 일치
    def test_brand_match(self):
        result = compare_brand_domain(
            "https://example.com/login",
            ["테스트브랜드"]
        )

        self.assertEqual(result["status"], "matched")

    # 9. 가짜 도메인 불일치
    def test_brand_mismatch(self):
        result = compare_brand_domain(
            "https://example.com.evil.example",
            ["테스트브랜드"]
        )

        self.assertEqual(result["status"], "mismatched")

    # 10. 등록되지 않은 브랜드
    def test_unknown_brand(self):
        result = compare_brand_domain(
            "https://example.com",
            ["없는브랜드"]
        )

        self.assertEqual(result["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
