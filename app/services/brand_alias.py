"""Map brand text that only *contains* a registered brand to that brand ("네이버 웹툰" -> "네이버").

The official-domain comparison (brand_domain.py) only matches exact brand names, but OCR and people often
read a service or branch name along with the brand: "네이버 웹툰", "스타벅스 강남점", "NAVER Pay", "네이버웹툰".
This adds the registered name so the comparison can run; the original text is kept as well.
"""
import json
import re
from pathlib import Path

OFFICIAL_DOMAINS = Path(__file__).resolve().parent.parent / "data" / "official_domains.json"
_SEPARATORS = re.compile(r"[\s·・/|,()\[\]{}<>:\-_&+]+")
# A prefix match without a separator ("네이버웹툰") is only trusted for non-Latin names of 2+ characters;
# Latin names must be a whole word so "naverx" or "cupid" do not match "naver" or "cu".
_MIN_PREFIX = 2


def registered_brands():
    try:
        names = json.loads(OFFICIAL_DOMAINS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [name for name in names if isinstance(name, str) and name.strip()]


def find_registered(text, brands=None):
    """Registered brand name contained in text, preferring the longest; None if there is none."""
    if not isinstance(text, str) or not text.strip():
        return None
    brands = registered_brands() if brands is None else brands
    folded = " ".join(text.split()).casefold()
    tokens = [t for t in _SEPARATORS.split(folded) if t]
    compact = "".join(tokens)
    for brand in sorted(brands, key=len, reverse=True):
        key = " ".join(brand.split()).casefold()
        if folded == key or key in tokens:
            return brand
        if not key.isascii() and len(key) >= _MIN_PREFIX and any(t.startswith(key) for t in tokens + [compact]):
            return brand
    return None


def expand_brand_texts(texts, limit=30):
    """texts plus the registered brand each one contains (deduplicated, original order first)."""
    brands = registered_brands()
    out, seen = [], set()
    for text in list(texts) + [find_registered(t, brands) for t in texts]:
        if isinstance(text, str) and text.strip() and text.casefold() not in seen:
            seen.add(text.casefold())
            out.append(text)
    return out[:limit]
