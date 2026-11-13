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


# Lookalike (typosquatting) brands: "nav3r", "starbuks", "edlya". Characters that look alike are folded first,
# then one edit (two for long words) is allowed. Short words are skipped: too many real words are one edit away.
_HOMOGLYPHS = str.maketrans({"0": "o", "1": "l", "i": "l", "|": "l", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "9": "g"})
_MIN_LOOKALIKE = 5


def _fold(text):
    return text.translate(_HOMOGLYPHS).replace("rn", "m").replace("vv", "w")


def _edit_distance(a, b, limit, sub_cost=1):
    """Optimal string alignment distance (swaps count as one edit); stops early above limit.
    sub_cost=2 makes a plain letter substitution cost two edits, so "never"/"saver" are not one edit from "naver"."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev2, prev = None, list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (sub_cost if ca != cb else 0))
            if i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        if min(cur) > limit:
            return limit + 1
        prev2, prev = prev, cur
    return prev[-1]


def _lookalike(host, suffix, brand_words):
    """(brand word, domain part that looks like it) or None. Labels are split on dots and hyphens."""
    name = host[: -len(suffix) - 1] if suffix and host.endswith("." + suffix) else host
    parts = [p for p in re.split(r"[.\-]", name) if p and p != "www"]
    for word in brand_words:
        if len(word) < _MIN_LOOKALIKE:
            continue
        target = _fold(word)
        # Long names: up to two edits of any kind. Short names: one swap/insertion/deletion only,
        # because a single replaced letter turns many short brands into real words.
        limit, sub_cost = (2, 1) if len(word) >= 8 else (1, 2)
        for part in parts:
            if part == word:
                continue
            folded = _fold(part)
            if folded == target or _edit_distance(folded, target, limit, sub_cost) <= limit:
                return word, part
    return None


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
                    result["brand_in_domain"] = {"word": word, "official": sorted(domains), "match": "contains", "found": word}
                    break
        if result["brand_in_domain"] is None:
            hit = _lookalike(host, ext.suffix, brand_words)
            if hit:
                word, found = hit
                result["brand_in_domain"] = {"word": word, "official": sorted(brand_words[word]), "match": "lookalike", "found": found}
        for word in PHISHING_WORDS:
            if word in ext.domain and word not in result["domain_keywords"]:
                result["domain_keywords"].append(word)
        rest = (ext.subdomain + " " + unquote(parts.path) + " " + unquote(parts.query)).lower()
        for word in PHISHING_WORDS:
            if re.search(re.escape(word), rest) and word not in result["path_keywords"] + result["domain_keywords"]:
                result["path_keywords"].append(word)
    return result
