"""Local URL/brand/store checks; no target HTTP or AI requests."""
from app.services.brand_domain import compare_brand_domain
from app.services.domain_impersonation import check_domain_impersonation
from app.services.redirect_patterns import check_redirect_patterns
from app.services.risk_signals import build_risk_signals
from app.services.store_qr_verifier import verify_store_qr
from app.services.suspicious_patterns import check_suspicious_patterns
from app.services.url_parser import parse_qr_url


def analyze_url_signals(qr_text: str, brand_texts: list[str], store_id: str | None = None) -> dict:
    errors = []

    def registry_check(function, code, *args):
        try:
            return function(*args)
        except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError):
            # Local registry files may be missing, unreadable or malformed.
            # Never expose file paths or turn missing evidence into a safe match.
            errors.append(code)
            return {"status": "unknown", "reason": "검사 DB를 읽거나 해석하지 못했습니다."}

    url_info = parse_qr_url(qr_text)
    analysis = {
        "url_info": url_info,
        "suspicious_patterns": check_suspicious_patterns(qr_text),
        "brand_domain": registry_check(compare_brand_domain, "BRAND_DB_UNAVAILABLE", qr_text, brand_texts),
        "store_qr": None,
        "domain_impersonation": None,
        "redirect_patterns": check_redirect_patterns(qr_text),
    }
    if store_id:
        analysis["store_qr"] = registry_check(verify_store_qr, "STORE_DB_UNAVAILABLE", qr_text, store_id)
        analysis["domain_impersonation"] = registry_check(
            check_domain_impersonation, "IMPERSONATION_DB_UNAVAILABLE", qr_text, store_id)
    return {
        "status": "invalid_url" if not url_info["valid"] else "partial" if errors else "ok",
        **analysis,
        "risk_signals": build_risk_signals(analysis),
        "errors": errors,
    }
