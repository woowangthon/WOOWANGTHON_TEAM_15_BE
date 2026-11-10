"""Constrained behavior classification and evidence validation, independent of URL/brand scoring."""
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AttackType = Literal["credential_theft", "personal_data_theft", "financial_fraud", "unsafe_installation"]
Severity = Literal["none", "weak", "moderate", "strong", "unknown"]
ATTACK_TYPES = ("credential_theft", "personal_data_theft", "financial_fraud", "unsafe_installation")
SEVERITY_POINTS = {"none": 0, "weak": 10, "moderate": 30, "strong": 60, "unknown": None}
ATTACK_NAMES = {"credential_theft": "인증정보 탈취", "personal_data_theft": "개인정보 탈취",
                "financial_fraud": "금전 피해 유도", "unsafe_installation": "위험한 설치 유도"}
CUES = {
    "credential_theft": r"비밀번호|패스워드|암호|OTP|인증\s*번호|복구\s*문구|시드\s*문구|password|verification\s*code|recovery\s*phrase|seed\s*phrase|private\s*key",
    "personal_data_theft": r"주민\s*등록|신분증|여권|생년월일|개인정보|passport|social\s*security|national\s*id|personal\s*(data|information)",
    "financial_fraud": r"송금|입금|이체|결제|계좌|카드\s*번호|payment|transfer|deposit|bank\s*account|credit\s*card|wire\s*money",
    "unsafe_installation": r"설치|다운로드|원격\s*제어|install|download|remote\s*(access|control)|antivirus",
}
ACTION = r"입력|제출|보내|전송|인증|송금|입금|이체|결제|설치|해제|끄|차단|정지|삭제|enter|submit|send|verify|pay|transfer|install|disable|turn\s*off"
STRONG_CONTEXT = r"긴급|즉시|정지|차단|삭제|환불|보상|복구\s*문구|시드\s*문구|보안.{0,15}(해제|끄)|urgent|immediately|suspend|blocked|refund|reward|seed\s*phrase|recovery\s*phrase|disable.{0,20}(security|antivirus)"


class AttackAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: AttackType
    severity: Severity
    evidence_ids: list[str] = Field(max_length=8)


class BehaviorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attacks: list[AttackAssessment] = Field(min_length=4, max_length=4)


def supported_types(text):
    return [kind for kind, pattern in CUES.items() if re.search(pattern, text, re.I)]


def unknown_attacks():
    return [{"type": kind, "severity": "unknown", "evidence_ids": []} for kind in ATTACK_TYPES]


def validate_assessment(raw, evidence):
    assessment = BehaviorResponse.model_validate_json(raw)
    if {attack.type for attack in assessment.attacks} != set(ATTACK_TYPES):
        raise ValueError("Missing or repeated attack type")
    available = {item["id"]: item for item in evidence}
    for attack in assessment.attacks:
        ids = attack.evidence_ids
        if len(set(ids)) != len(ids) or not set(ids).issubset(available):
            raise ValueError("Unknown or repeated evidence ID")
        if attack.severity in {"none", "unknown"}:
            if ids:
                raise ValueError("Unscored classification must not claim evidence")
            continue
        if not ids or not any(attack.type in available[i]["supports"] for i in ids):
            raise ValueError("No supporting category cue")
        text = " ".join(available[i]["text"] for i in ids if available[i]["kind"] == "page_text")
        # A form or executable link alone cannot support moderate/strong risk.
        if attack.severity in {"moderate", "strong"}:
            if not text or not re.search(ACTION, text, re.I):
                raise ValueError("No observed textual request")
        if attack.severity == "strong" and not re.search(STRONG_CONTEXT, text, re.I):
            raise ValueError("Strong classification lacks coercion/deception context")
    return [attack.model_dump() for attack in assessment.attacks]
