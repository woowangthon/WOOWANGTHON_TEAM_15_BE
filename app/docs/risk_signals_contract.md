# QR Guard 위험 신호 데이터 명세

## API 경로

- `POST /api/url/analyze`: URL 패턴·브랜드·매장 QR 검사 결과와 `risk_signals` 반환
- `GET /api/stores/search?keyword=테스트카페`: 등록된 매장 이름 검색
- `POST /api/analyze`: 같은 URL 검사를 서버 내부 공통 함수로 실행하고 도메인·TLS·국가·선택적 AI 행동 점수와 함께 반환합니다.
  URL 검사 결과는 `url_analysis`, 실제 최종 이동 주소의 검사 결과는 `final_url_analysis`(미수행 시 null)에 있습니다.

```json
{
  "qr_text": "https://menu.example.com/store/demo-cafe-01?table=3",
  "brand_texts": [],
  "store_id": "demo-cafe-01"
}
```

`store_id`는 선택 항목입니다. 이 API의 위험 신호는 기존 점수에 자동 합산되지 않습니다.

## 목적

URL 분석 담당자가 탐지한 위험 징후를
위험도 계산 담당자에게 전달하기 위한 데이터 형식입니다.

## 전달 데이터 예시

```json
{
  "url_valid": true,
  "suspicious_url_pattern": false,
  "pattern_codes": [],
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

## 기계 판독용 패턴 코드

`suspicious_patterns.codes`와 `risk_signals.pattern_codes`에 같은 목록을 반환합니다.

| 코드 | 관찰 내용 |
| --- | --- |
| IP_LITERAL | 도메인 대신 IP 주소 사용 |
| SHORT_URL | 알려진 단축 URL 서비스 사용 |
| EXECUTABLE_LINK | URL 경로의 실행·설치 파일 확장자 |
| EXECUTABLE_QUERY | 쿼리 매개변수의 실행·설치 파일 확장자 |
| USERINFO_IN_URL | 사용자 정보(@)가 포함된 URL. 통합 API에서는 수집 전에 거부 |

형식이 잘못되어 검사하지 못하면 suspicious_url_pattern=null이며 코드 목록이 비어 있어도 안전을 뜻하지 않습니다.
문자열 설명을 비교해 점수를 계산하지 않고 코드를 사용하도록 준비한 계약입니다.

## 실패·점수 범위

로컬 DB를 읽거나 해석하지 못하면 해당 비교 결과는 unknown으로 유지하고 errors에
BRAND_DB_UNAVAILABLE / STORE_DB_UNAVAILABLE / IMPERSONATION_DB_UNAVAILABLE을 반환합니다.
이 경우 URL 분석 status=partial이며 메타데이터/AI 분석 결과는 유지됩니다.
URL 분석 status=ok와 matched는 안전 판정이 아닙니다.

통합 응답 score_scope=ai_behavior_tls_domain_age이며 behavior-v1 배점은 변경하지 않았습니다.
score/level/assessment_status/analysis_complete는 behavior-v1 범위이고 URL 검사의 status와 별개입니다.
따라서 낮은 점수만으로 URL·브랜드·매장 신호가 없다고 판단하면 안 됩니다.
최종 이동 주소를 재검사해도 URL 신호를 현재 점수에 중복 가산하지 않습니다.
