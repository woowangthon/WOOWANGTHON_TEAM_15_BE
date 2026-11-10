"""Documented response contracts shared with the separate Expo repository."""
from typing import Literal

from pydantic import BaseModel, Field

from app.behavior import AttackAssessment, AttackType

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


class AnalyzeResponse(BaseModel):
    url: str
    hostname: str
    evidence: Evidence
    score: int | None = Field(ge=0, le=100)
    score_version: Literal["behavior-v1"]
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
