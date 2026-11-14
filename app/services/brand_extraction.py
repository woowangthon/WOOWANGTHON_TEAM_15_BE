"""Match registered aliases using exact letters, Unicode normalization and word boundaries."""
import json
import re
import unicodedata
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


class BrandRegistryUnavailable(Exception):
    pass


def load_aliases():
    try:
        aliases = json.loads((DATA_DIR / "brand_aliases.json").read_text(encoding="utf-8"))
        domains = json.loads((DATA_DIR / "official_domains.json").read_text(encoding="utf-8"))
        if not isinstance(aliases, dict) or not isinstance(domains, dict):
            raise ValueError("Invalid registry")
        result = {}
        for brand, names in aliases.items():
            if brand not in domains or not isinstance(names, list) or not names:
                raise ValueError("Unregistered brand alias")
            if not all(isinstance(name, str) and 1 <= len(name) <= 100 for name in names):
                raise ValueError("Invalid aliases")
            result[brand] = list(dict.fromkeys([brand, *names]))
        return result
    except (OSError, UnicodeError, ValueError, TypeError):
        raise BrandRegistryUnavailable("상표 비교 정보를 읽지 못했습니다.") from None


def normalize_text(text):
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def label_text(text):
    text = unicodedata.normalize("NFKC", text)
    # A printed URL/email alone must not establish which brand owns the QR.
    text = re.sub(r"(?:https?://|www\.)\S+|[\w.+-]+@[\w.-]+\.[a-z]{2,}", " ", text, flags=re.I)
    text = re.sub(r"(?<!\w)(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/\S*)?", " ", text, flags=re.I)
    return normalize_text(text)


def extract_brand_candidates(blocks):
    aliases = load_aliases()
    best = {}
    for brand, names in aliases.items():
        patterns = []
        for alias in names:
            letters = normalize_text(alias).replace(" ", "")
            if letters:
                patterns.append(re.compile(r"(?<!\w)" + r"\s*".join(map(re.escape, letters)) + r"(?!\w)"))
        for block in blocks:
            text = label_text(block["text"])
            if any(pattern.search(text) for pattern in patterns):
                candidate = {"brand": brand, "matched_text": block["text"], "ocr_confidence": block["confidence"]}
                if brand not in best or candidate["ocr_confidence"] > best[brand]["ocr_confidence"]:
                    best[brand] = candidate
    return sorted(best.values(), key=lambda item: (-item["ocr_confidence"], item["brand"]))[:10]
