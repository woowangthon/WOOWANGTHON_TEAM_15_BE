"""Suspicious words in the QR's domain name (P1-8).

1. Brand inside a non-official domain: "naver-event.xyz", "naver.com.login-check.xyz", "starbucks-coupon.com".
   Brand words come from the official-domain DB ("naver.com" -> "naver"), so this works even when the person
   entered no brand name. The brand's own official domains (and their subdomains) are never flagged.
2. Phishing words in the registered domain name itself: "secure-login-verify.com", "parcel-delivery-check.net".
   Only the registered domain counts; "login.naver.com" or "naver.com/login" are common on real sites, so words
   in subdomains or the path are reported for information only and add no points.
Kept separate from suspicious_patterns.py (task 2) so it can be moved there later without changing its codes.
"""
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from app.security import EXTRACT

OFFICIAL_DOMAINS = Path(__file__).resolve().parent.parent / "data" / "official_domains.json"
MIN_BRAND_WORD = 4  # shorter words ("cu", "kb") match too many unrelated domains
PHISHING_WORDS = (
    "login", "signin", "logon", "verify", "verification", "secure", "security", "account", "update",
    "confirm", "unlock", "suspend", "wallet", "refund", "payment", "banking", "delivery", "parcel",
    "customs", "invoice", "reward", "prize", "giftcard", "coupon", "support-center",
)


def _brand_words():
    """{'naver': {'naver.com'}, 'starbucks': {'starbucks.co.kr'}, ...} from the official-domain DB."""
    try:
        data = json.loads(OFFICIAL_DOMAINS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    words = {}
    for brand, domains in data.items():
        if "테스트" in brand or not isinstance(domains, list):  # demo entries (example.com) are not real brands
            continue
        for domain in domains:
            parts = EXTRACT(str(domain).lower())
            if parts.domain and len(parts.domain) >= MIN_BRAND_WORD:
                words.setdefault(parts.domain, set()).add(parts.top_domain_under_public_suffix)
    return words


def check_domain_keywords(urls):
    """urls: the scanned URL and, if any, the final URL after redirects."""
    brand_words = _brand_words()
    official = {d for domains in brand_words.values() for d in domains}
    result = {"brand_in_domain": None, "domain_keywords": [], "path_keywords": []}
    for url in (u for u in urls if u):
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        ext = EXTRACT(host)
        registered = ext.top_domain_under_public_suffix
        if not registered or registered in official:
            continue  # IP addresses / unknown suffixes, or an official brand domain
        if result["brand_in_domain"] is None:
            for word, domains in brand_words.items():
                if word in host:
                    result["brand_in_domain"] = {"word": word, "official": sorted(domains)}
                    break
        for word in PHISHING_WORDS:
            if word in ext.domain and word not in result["domain_keywords"]:
                result["domain_keywords"].append(word)
        rest = (ext.subdomain + " " + unquote(parts.path) + " " + unquote(parts.query)).lower()
        for word in PHISHING_WORDS:
            if re.search(re.escape(word), rest) and word not in result["path_keywords"] + result["domain_keywords"]:
                result["path_keywords"].append(word)
    return result
