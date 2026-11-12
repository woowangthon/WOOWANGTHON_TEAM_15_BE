"""Typed task-2 results shared by standalone and combined analysis endpoints."""
from typing import Any, Literal

from pydantic import BaseModel, Field

PatternCode = Literal["IP_LITERAL", "SHORT_URL", "EXECUTABLE_LINK", "EXECUTABLE_QUERY", "USERINFO_IN_URL"]
BrandStatus = Literal["matched", "mismatched", "unknown", "invalid_url"]
StoreStatus = Literal["matched", "mismatched", "unknown", "invalid_url", "not_checked"]
ImpersonationStatus = Literal["host_matched", "impersonation_suspected", "other_domain", "unknown", "invalid_url", "not_checked"]


class PatternReport(BaseModel):
    valid: bool
    suspicious: bool | None
    codes: list[PatternCode] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class RiskSignals(BaseModel):
    url_valid: bool | None
    suspicious_url_pattern: bool | None
    pattern_codes: list[PatternCode] = Field(default_factory=list)
    brand_domain_status: BrandStatus
    store_qr_status: StoreStatus
    store_data_verified: bool | None
    domain_impersonation_status: ImpersonationStatus
    redirect_pattern_detected: bool | None


class URLAnalysisResponse(BaseModel):
    # ok means processing succeeded, never that the URL is safe.
    status: Literal["ok", "partial", "invalid_url"]
    url_info: dict[str, Any]
    suspicious_patterns: PatternReport
    brand_domain: dict[str, Any]
    store_qr: dict[str, Any] | None = None
    domain_impersonation: dict[str, Any] | None = None
    redirect_patterns: dict[str, Any]
    risk_signals: RiskSignals
    errors: list[str] = Field(default_factory=list)
