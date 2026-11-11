
import unittest

from app.services.redirect_patterns import check_redirect_patterns


class TestRedirectPatterns(unittest.TestCase):

    # 1. 외부 사이트 이동 유도 패턴
    def test_external_redirect(self):
        result = check_redirect_patterns(
            "https://menu.example.com/redirect?"
            "url=https%3A%2F%2Ffake.example%2Fpay"
        )

        self.assertTrue(result["suspicious"])

    # 2. 일반적인 카페 메뉴 URL
    def test_normal_menu_url(self):
        result = check_redirect_patterns(
            "https://menu.example.com/menu?table=3"
        )

        self.assertFalse(result["suspicious"])

    # 3. 같은 호스트로 이동하는 주소
    def test_same_host_redirect(self):
        result = check_redirect_patterns(
            "https://menu.example.com/redirect?"
            "url=https%3A%2F%2Fmenu.example.com%2Fhelp"
        )

        self.assertFalse(result["suspicious"])

    # 4. 잘못된 URL
    def test_invalid_url(self):
        result = check_redirect_patterns(
            "not-a-url"
        )

        self.assertFalse(result["valid"])
        self.assertIsNone(result["suspicious"])


if __name__ == "__main__":
    unittest.main()
