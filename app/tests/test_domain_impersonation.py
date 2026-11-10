
import unittest

from app.services.domain_impersonation import check_domain_impersonation


class TestDomainImpersonation(unittest.TestCase):

    # 1. 등록된 정상 호스트
    def test_normal_domain(self):
        result = check_domain_impersonation(
            "https://menu.example.com/store/demo-cafe-01",
            "demo-cafe-01"
        )

        self.assertEqual(result["status"], "host_matched")

    # 2. 공식 호스트명을 앞에 붙인 위장 도메인
    def test_fake_subdomain(self):
        result = check_domain_impersonation(
            "https://menu.example.com.evil.example",
            "demo-cafe-01"
        )

        self.assertEqual(
            result["status"], "impersonation_suspected"
        )

    # 3. 숫자로 문자를 바꾼 유사 도메인
    def test_similar_domain(self):
        result = check_domain_impersonation(
            "https://menu.examp1e.com",
            "demo-cafe-01"
        )

        self.assertEqual(
            result["status"], "impersonation_suspected"
        )

    # 4. 전혀 다른 도메인
    def test_other_domain(self):
        result = check_domain_impersonation(
            "https://completely-different.example",
            "demo-cafe-01"
        )

        self.assertEqual(result["status"], "other_domain")

    # 5. 등록되지 않은 매장
    def test_unknown_store(self):
        result = check_domain_impersonation(
            "https://menu.example.com",
            "unknown-cafe"
        )

        self.assertEqual(result["status"], "unknown")

    # 6. 잘못된 URL
    def test_invalid_url(self):
        result = check_domain_impersonation(
            "not-a-url",
            "demo-cafe-01"
        )

        self.assertEqual(result["status"], "invalid_url")


if __name__ == "__main__":
    unittest.main()
