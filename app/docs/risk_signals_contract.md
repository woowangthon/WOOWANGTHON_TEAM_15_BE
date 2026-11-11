# QR Guard 위험 신호 데이터 명세

## 목적

URL 분석 담당자가 탐지한 위험 징후를
위험도 계산 담당자에게 전달하기 위한 데이터 형식입니다.

## 전달 데이터 예시

```json
{
  "url_valid": true,
  "suspicious_url_pattern": false,
  "brand_domain_status": "unknown",
  "store_qr_status": "matched",
  "store_data_verified": false,
  "domain_impersonation_status": "host_matched",
  "redirect_pattern_detected": false
}
```

## 값의 의미

- true: 해당 조건이 확인됨
- false: 해당 조건이 확인되지 않음
- null: 검사가 수행되지 않았거나 판단할 수 없음

## 주요 상태값

store_qr_status:

- matched: 등록된 주소 비교 규칙과 일치
- mismatched: 등록된 주소와 불일치
- unknown: 등록 정보가 없어 확인 불가
- invalid_url: URL 형식 오류
- not_checked: 검사 미수행

domain_impersonation_status:

- host_matched: 등록된 호스트명과 일치
- impersonation_suspected: 위장 도메인 의심
- other_domain: 등록된 호스트명과 다름
- unknown: 등록 정보 없음
- invalid_url: URL 형식 오류
- not_checked: 검사 미수행

## 주의사항

1. matched는 안전 판정이 아닙니다.
2. store_data_verified가 false 또는 null이면
   매장 인증을 안전성의 근거로 사용하지 않습니다.
3. unknown과 not_checked는 위험 없음이 아닙니다.
4. 위험도 점수는 별도의 위험도 계산 기능에서 산정합니다.
5. URL 분석 과정에서는 대상 사이트에 직접 접속하지 않습니다.
