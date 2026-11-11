
# URL 분석 결과를 위험도 계산용 데이터로 정리

def build_risk_signals(analysis: dict) -> dict:

    # 1. 각 검사 결과 가져오기
    url_info = analysis.get("url_info") or {}
    suspicious = analysis.get("suspicious_patterns") or {}
    brand = analysis.get("brand_domain") or {}
    store = analysis.get("store_qr") or {}
    impersonation = analysis.get("domain_impersonation") or {}
    redirect = analysis.get("redirect_patterns") or {}

    # 2. 위험도 계산 담당자에게 전달할 데이터
    return {
        "url_valid": url_info.get("valid"),
        "suspicious_url_pattern": suspicious.get("suspicious"),
        "brand_domain_status": brand.get("status", "unknown"),
        "store_qr_status": store.get("status", "not_checked"),
        "store_data_verified": store.get("is_store_verified"),
        "domain_impersonation_status": impersonation.get(
            "status", "not_checked"
        ),
        "redirect_pattern_detected": redirect.get("suspicious")
    }
