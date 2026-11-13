"""Compare web addresses printed next to a QR (read from a photo) with the QR's own address.

A classic quishing trick is a fake QR sticker on a genuine poster: the printed text still shows the real
site while the QR points elsewhere. Only registered domains are compared (m.starbucks.co.kr == starbucks.co.kr),
so paths, subdomains and OCR noise around them do not matter.
"""
import re
from urllib.parse import urlsplit

from app.security import EXTRACT

MAX_PRINTED = 5
_HOST_RE = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")


def registered_domain(text):
    """'https://www.Starbucks.co.kr/menu' -> 'starbucks.co.kr'; None for anything that is not a public domain."""
    if not isinstance(text, str):
        return None
    value = text.strip().strip(".,;:!?()[]<>\"'").lower()
    if not value or len(value) > 253 or " " in value:
        return None
    host = urlsplit(value if "://" in value else "http://" + value).hostname or ""
    try:
        host = host.encode("idna").decode("ascii")  # 한글.kr -> xn--...
    except UnicodeError:
        return None
    if not _HOST_RE.match(host):
        return None
    domain = EXTRACT(host).top_domain_under_public_suffix
    return domain or None


def normalize_printed(texts):
    """Distinct registered domains from printed texts, at most MAX_PRINTED."""
    domains = []
    for text in texts or []:
        domain = registered_domain(text)
        if domain and domain not in domains:
            domains.append(domain)
        if len(domains) == MAX_PRINTED:
            break
    return domains


def compare_printed_domains(qr_urls, printed_texts):
    """qr_urls: the scanned URL and, if any, the final URL after redirects."""
    printed = normalize_printed(printed_texts)
    qr_domains = [d for d in (registered_domain(u) for u in qr_urls if u) if d]
    if not printed:
        return {"status": "not_checked", "printed": [], "qr_domain": qr_domains[0] if qr_domains else None}
    status = "matched" if any(d in printed for d in qr_domains) else "mismatched"
    return {"status": status, "printed": printed, "qr_domain": qr_domains[0] if qr_domains else None}
