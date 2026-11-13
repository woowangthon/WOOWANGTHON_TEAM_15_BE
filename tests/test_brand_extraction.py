import unittest

from app.services.brand_extraction import extract_brand_candidates

BOX = [[2, 2], [95, 2], [95, 35], [2, 35]]


def block(text, confidence=0.95):
    return {"text": text, "confidence": confidence, "bounding_box": BOX}


class BrandExtractionTests(unittest.TestCase):
    def test_korean_english_and_unicode_aliases_are_canonicalized(self):
        for text in ["STARBUCKS COFFEE", "스타 벅스", "ＳＴＡＲＢＵＣＫＳ"]:
            with self.subTest(text=text):
                found = extract_brand_candidates([block(text)])
                self.assertEqual([item["brand"] for item in found], ["스타벅스"])
        self.assertEqual(extract_brand_candidates([block("EDIYA COFFEE")])[0]["brand"], "이디야")

    def test_deduplicate_and_keep_best_confidence(self):
        found = extract_brand_candidates([block("NAVER", 0.7), block("네이버", 0.9)])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["ocr_confidence"], 0.9)

    def test_urls_emails_and_substrings_do_not_establish_brand_identity(self):
        for text in ["https://naver.com", "naver.com", "www.naver.com", "user@naver.com", "NAVERFAKE", "ＨＴＴＰＳ://naver.com"]:
            with self.subTest(text=text):
                self.assertEqual(extract_brand_candidates([block(text)]), [])

if __name__ == "__main__":
    unittest.main()
