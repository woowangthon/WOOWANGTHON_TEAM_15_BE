"""Versioned server-owned scores: max AI behavior + TLS + domain age, never URL/brand heuristics."""
from app.behavior import ATTACK_NAMES, SEVERITY_POINTS, unknown_attacks

SCORE_VERSION = "behavior-v1"


def score_metadata(url, evidence):
    tls = evidence["tls"]
    rdap = evidence["rdap"]
    reasons = []
    if tls["status"] == "invalid":
        tls_points = 25
        reasons.append({"code": "INVALID_TLS", "points": 25, "message": "TLS 인증서 검증에 실패했습니다.", "evidence_ids": ["tls"]})
    elif url.lower().startswith("http://"):
        tls_points = 10
        reasons.append({"code": "NO_HTTPS", "points": 10, "message": "HTTPS를 사용하지 않습니다.", "evidence_ids": ["tls"]})
    elif tls["status"] == "ok":
        tls_points = 0
    else:
        tls_points = None

    if rdap["status"] == "ok" and isinstance(rdap.get("age_days"), int):
        age = rdap["age_days"]
        domain_points = 15 if age < 30 else 5 if age < 180 else 0
        if domain_points:
            reasons.append({"code": "NEW_DOMAIN" if age < 30 else "YOUNG_DOMAIN",
                            "points": domain_points, "message": "도메인이 생성된 지 30일 미만입니다." if age < 30 else "도메인이 생성된 지 180일 미만입니다.",
                            "evidence_ids": ["rdap"]})
    elif rdap["status"] == "not_applicable":
        domain_points = 0
    else:
        domain_points = None
    complete = all(item["status"] in {"ok", "invalid", "not_applicable"} for item in evidence.values())
    blocked = evidence["dns"]["status"] == "blocked"
    components = {"ai_behavior": None, "tls": None if blocked else tls_points,
                  "domain_age": None if blocked else domain_points}
    if blocked:
        reasons = [{"code": "BLOCKED_TARGET", "points": 0, "message": "내부 네트워크 접근 방지를 위해 검사를 차단했습니다.", "evidence_ids": ["dns"]}]
    return finalize(components, reasons, unknown_attacks(), evidence_complete=complete,
                    behavior_complete=False, navigation_allowed=not blocked)


def finalize(components, reasons, attacks, *, evidence_complete, behavior_complete, navigation_allowed):
    known = [value for value in components.values() if value is not None]
    score = sum(known) if known else None
    status = "complete" if evidence_complete and behavior_complete and navigation_allowed else "partial" if known else "failed"
    level = ("위험" if score is not None and score >= 50 else
             "주의" if score is not None and score >= 20 else
             "낮음" if status == "complete" else "확인 불가")
    return {"score": score, "score_version": SCORE_VERSION, "components": components,
            "assessment_status": status, "level": level, "reasons": reasons,
            "attack_types": attacks, "evidence_complete": evidence_complete,
            "analysis_complete": status == "complete", "navigation_allowed": navigation_allowed,
            "auto_open": False, "requires_confirmation": True,
            "warning": "점수는 악성 확률이 아닙니다. 일부 정보가 누락될 수 있으며 접속 전 사용자 확인이 필요합니다."}


def combine_page(result, page, target=None):
    components = {**result["components"]}
    reasons = [dict(item) for item in result["reasons"]]
    if target is not None:
        for component, codes in [("tls", {"INVALID_TLS", "NO_HTTPS"}), ("domain_age", {"NEW_DOMAIN", "YOUNG_DOMAIN"})]:
            current = components[component]
            other = target["components"][component]
            if other is not None and (current is None or other > current):
                components[component] = other
                reasons = [r for r in reasons if r["code"] not in codes]
                reasons.extend({**r, "evidence_ids": ["final_" + i for i in r.get("evidence_ids", [])],
                                "message": "최종 이동 주소: " + r["message"]}
                               for r in target["reasons"] if r["code"] in codes)
    attacks = page.get("attack_types", unknown_attacks())
    assessed = page["ai_status"] in {"generated", "cached"}
    if assessed:
        positive = [a for a in attacks if SEVERITY_POINTS[a["severity"]] is not None]
        best = max(positive, key=lambda a: SEVERITY_POINTS[a["severity"]], default=None)
        components["ai_behavior"] = SEVERITY_POINTS[best["severity"]] if best else None
        if best and components["ai_behavior"]:
            reasons.append({"code": "AI_" + best["type"].upper() + "_" + best["severity"].upper(),
                            "points": components["ai_behavior"],
                            "message": ATTACK_NAMES[best["type"]] + " 관련 행동 신호: " + best["severity"],
                            "evidence_ids": list(best["evidence_ids"])})
    blocked = page["status"] == "blocked" or (target is not None and not target["navigation_allowed"])
    evidence_complete = result.get("evidence_complete", False) and (target is None or target.get("evidence_complete", False))
    behavior_complete = (page["status"] == "ok" and not page.get("meta_refresh", False)
                         and assessed and all(a["severity"] != "unknown" for a in attacks))
    scored = finalize(components, reasons, attacks, evidence_complete=evidence_complete,
                      behavior_complete=behavior_complete,
                      navigation_allowed=result["navigation_allowed"] and not blocked)
    return {**result, **scored, "page": page}
