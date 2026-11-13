"""Documented response contracts shared with the separate Expo repository."""
from typing import Literal

from pydantic import BaseModel, Field

from app.behavior import AttackAssessment, AttackType
from app.url_models import URLAnalysisResponse

CheckStatus = Literal["ok", "unknown", "blocked", "invalid", "not_applicable"]


class Check(BaseModel):
    status: CheckStatus
    reason: str | None = None


class DNSCheck(Check):
    addresses: list[str] = Field(default_factory=list)


class RDAPCheck(Check):
    domain: str | None = None
    created_at: str | None = None
    age_days: int | None = None


class TLSCheck(Check):
    valid: bool | None = None
    expires_at: str | None = None
    expires_in_days: int | None = None
    checked_ip: str | None = None
    protocol: str | None = None
    issuer: str | None = None


class Country(BaseModel):
    ip: str
    country_code: str | None = None
    is_overseas: bool | None = None


class GeoIPCheck(Check):
    countries: list[Country] = Field(default_factory=list)
    is_overseas: bool | None = None
    database_updated_at: str | None = None
    note: str | None = None


class Evidence(BaseModel):
    dns: DNSCheck
    rdap: RDAPCheck
    tls: TLSCheck
    geoip: GeoIPCheck


class Reason(BaseModel):
    code: str
    points: int
    message: str
    evidence_ids: list[str] = Field(default_factory=list)


class RedirectHop(BaseModel):
    url: str
    http_status: int


class PageEvidence(BaseModel):
    id: str
    kind: Literal["page_text", "form", "link"]
    text: str
    supports: list[AttackType]


class Components(BaseModel):
    ai_behavior: int | None = Field(default=None, ge=0, le=60)
    tls: int | None = Field(default=None, ge=0, le=25)
    domain_age: int | None = Field(default=None, ge=0, le=15)


class PageReport(BaseModel):
    status: CheckStatus
    reason: str | None = None
    final_url: str | None = None
    final_hostname: str | None = None
    final_evidence: Evidence | None = None
    redirect_chain: list[RedirectHop] = Field(default_factory=list)
    http_status: int | None = None
    bytes_read: int | None = None
    download_response: bool = False
    findings: list[Reason] = Field(default_factory=list)
    evidence: list[PageEvidence] = Field(default_factory=list)
    attack_types: list[AttackAssessment] = Field(default_factory=list)
    readable: bool | None = None
    password_fields: int = 0
    meta_refresh: bool = False
    coverage: str | None = None
    ai_status: Literal["generated", "cached", "disabled", "unavailable", "skipped"]
    ai_model: str | None = None
    ai_assessment: Literal["suspicious", "no_obvious_signals", "inconclusive"]
    ai_explanation: str | None = None


class VerdictReason(BaseModel):
    code: str
    points: int
    message: str


class Verdict(BaseModel):
    """combined-v1 overall verdict (app/verdict.py): behavior-v1 points + URL/brand/store signals."""
    version: Literal["combined-v1"]
    score: int | None = Field(ge=0, le=100)
    level: Literal["낮음", "주의", "위험", "확인 불가"]
    reasons: list[VerdictReason]


class PrintedDomainCheck(BaseModel):
    status: Literal["matched", "mismatched", "not_checked"]
    printed: list[str] = Field(default_factory=list, description="비교한 인쇄 주소의 등록 도메인")
    qr_domain: str | None = None


class BrandInDomain(BaseModel):
    word: str = Field(description="도메인에서 찾은 상표 단어 (예: naver)")
    official: list[str] = Field(description="그 상표의 공식 도메인")


class DomainKeywordCheck(BaseModel):
    brand_in_domain: BrandInDomain | None = None
    domain_keywords: list[str] = Field(default_factory=list, description="등록 도메인 이름 속 낚시성 단어 (점수 반영)")
    path_keywords: list[str] = Field(default_factory=list, description="하위 도메인·경로·쿼리 속 낚시성 단어 (참고만)")


class AnalyzeResponse(BaseModel):
    url: str
    hostname: str
    evidence: Evidence
    score: int | None = Field(ge=0, le=100)
    score_version: Literal["behavior-v1"]
    score_scope: Literal["ai_behavior_tls_domain_age"]
    url_analysis: URLAnalysisResponse
    final_url_analysis: URLAnalysisResponse | None = None
    assessment_status: Literal["complete", "partial", "failed"]
    components: Components
    attack_types: list[AttackAssessment]
    evidence_complete: bool
    level: Literal["낮음", "주의", "위험", "확인 불가"]
    reasons: list[Reason]
    analysis_complete: bool
    navigation_allowed: bool
    auto_open: Literal[False]
    requires_confirmation: Literal[True]
    warning: str
    ai_explanation: str
    ai_status: Literal["generated", "cached", "disabled", "unavailable", "skipped"]
    ai_model: str | None
    page: PageReport | None = None
    # Plain-language summary for the result screen. AI-written only when explanation_status is
    # generated/cached; otherwise it is the same rule-based text as ai_explanation.
    explanation: str
    explanation_status: Literal["generated", "cached", "disabled", "unavailable", "skipped"]
    explanation_model: str | None = None
    # Why no AI explanation was made, for the AI card: set when explanation_status is skipped (blocked target)
    # or unavailable (AI not configured, timeout, invalid response). None when disabled or generated.
    explanation_skip_reason: str | None = None
    # Overall verdict for the result screen. score/level above stay behavior-v1 for compatibility.
    verdict: Verdict
    # Web address printed next to the QR (from a photo) vs the QR's address. not_checked when none sent.
    printed_domain_check: PrintedDomainCheck
    # Brand / phishing words in a non-official domain name. Empty when nothing was found.
    domain_keyword_check: DomainKeywordCheck
