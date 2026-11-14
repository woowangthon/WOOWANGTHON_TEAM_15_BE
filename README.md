# QR Alert FastAPI backend

## 현재 점수 정책 (metadata-v2 / combined-v2)

현재 POST /api/analyze는 페이지 AI 행동 분석을 점수 및 검사 완료 조건에서 제외합니다.
루트 score는 TLS·도메인 생성일만 반영하고, 앱은 URL·공식 도메인·인쇄 주소·매장 신호를 더한 verdict.score를 표시합니다.
페이지 AI는 참고 정보로만 남고, 강한 위험/확인 불가 모두 점수와 종합 등급에 영향을 주지 않습니다.
공식 도메인 AI 검색은 계속 점수에 반영됩니다. TLS/RDAP/국가/공식 도메인 등 남은 필수 검사의 미확인은 유지됩니다.
점수 버전은 score_version=metadata-v2, score_scope=tls_domain_age, verdict.version=combined-v2입니다.
아래 behavior-v1/combined-v1 설명과 예시는 이전 정책의 기록입니다. [현재 정책과 검증](app/docs/metadata_scoring.md)을 먼저 참고하세요.


현재 QR 공식 도메인 판정은 **고정 JSON 비교 대신 매 스캔의 BAZE AI 웹 검색**을 사용합니다.
상표 미입력·기존 DB 미등록 상표도 검색하며, 출처가 부족하면 확인 불가로 남깁니다.
설정·출처 검증·점수 및 API 차이: [AI 도메인 확인](app/docs/ai_domain_verification.md).
공식 소유 관계 확인은 사이트의 합법성이나 전체 안전을 보증하지 않습니다.

이 저장소는 QR의 HTTP(S) URL을 받아 서버에서 도메인·TLS·IP 국가 정보를 조회하고,
선택적으로 정적 HTML과 AI를 이용해 요구 행동의 위험도를 평가합니다.
휴대폰 앱은 URL을 보내고 JSON을 받습니다. 2번의 URL 패턴·브랜드·매장 검사는
공통 서비스로 연결되어 한 요청에서 함께 실행됩니다.
사진의 상표명 OCR은 서버의 `/api/ocr/brands`에서 수행합니다.
QR 해독·사진 촬영 및 결과 화면·사용자 확인 후 URL 열기는 앱 담당 범위입니다.

## 실행

Python 3.11 이상, 저장소 루트 PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- GET /health: 서버 상태
- http://127.0.0.1:8000/docs : 요청/응답 모델과 실행 가능한 API 문서

## 설정

.env.example을 참고해 저장소 루트 .env를 설정하세요.
기존 환경 변수가 .env보다 우선합니다. 변경 후 서버를 재시작하세요.

```dotenv
BAZE_API_KEY=your-own-key
BAZE_BASE_URL=https://factchat-cloud.mindlogic.ai/v1/gateway
BAZE_MODEL=gpt-6-luna
GEOIP_DB_PATH=./data/GeoLite2-Country.mmdb
CORS_ORIGINS=http://localhost:8081
```

키·.env·국가 DB는 Git에 포함되지 않습니다. Expo의 EXPO*PUBLIC*\*에 AI 키를 넣지 마세요.
국가 DB 상대 경로는 터미널 위치가 아니라 저장소 루트를 기준으로 해석됩니다.
키와 Gateway 주소는 같은 BAZE 배포에서 발급된 조합이어야 합니다.

```powershell
.\.venv\Scripts\python.exe -m scripts.check_baze
.\.venv\Scripts\python.exe -m scripts.check_geoip
```

첫 명령은 모델 목록만 조회하고, 두 번째는 로컬 DB만 조회합니다.
국가 DB는 MaxMind GeoLite2 Country MMDB를 별도 확보하고 최신으로 갱신하세요.
데이터 출처: MaxMind, https://www.maxmind.com . 서비스 배포 시 이용·출처 표시 조건을 확인하세요.

## URL 패턴·매장 검사 API (2번 담당)

같은 FastAPI 서버에 다음 API를 함께 등록합니다.

| 경로                                        | 기능                                                              |
| ------------------------------------------- | ----------------------------------------------------------------- |
| `POST /api/analyze`                         | URL·브랜드·매장 검사 + 도메인·TLS·국가 정보 + 선택적 AI 행동 점수 |
| `POST /api/url/analyze`                     | URL 패턴·브랜드·매장 QR 비교 및 `risk_signals`                    |
| `GET /api/stores/search?keyword=테스트카페` | 등록된 매장 이름 검색                                             |
| `POST /api/ocr/brands`                      | 사진 속 상표명 후보 읽기 (AI 이미지 인식, 아래 참고)              |

### 사진 속 상표명 읽기 (`POST /api/ocr/brands`)
Expo Go에는 기기 내 OCR이 없어 서버의 AI 이미지 인식으로 상표명 후보를 읽습니다. 현재 앱이 사용하는 구현: `app/brand_ocr.py`, 테스트: `tests/test_brand_ocr.py`. BAZE_VISION_MODEL을 지정하면 OCR에만 별도 모델을 사용할 수 있고, 비우면 BAZE_MODEL을 사용합니다.
```json
{"image_base64": "<JPG/PNG/WebP base64, 원본 3MB 이하>"}
```
응답: `{"status": "ok|unavailable|invalid_image", "brands": [{"name": "스타벅스", "registered": true}], "domains": [{"text": "www.starbucks.co.kr", "domain": "starbucks.co.kr"}], "message": null}`
- `domains`는 사진에 글자로 인쇄된 웹 주소입니다(QR 무늬 안의 내용이 아님). 등록 도메인으로 정리해 최대 5개 반환합니다.
- 사용자가 "사진에서 찾기"를 누르거나, 앱에서 "QR 사진으로 상표·주소도 찾기"를 켰을 때만 전송합니다. 사진은 AI 게이트웨이에 한 번 보내고 저장·로그·캐시하지 않습니다.

### 인쇄된 주소와 QR 주소 비교 (`printed_domains`)
`POST /api/analyze`에 `printed_domains`(최대 10개)를 보내면 QR 주소(리디렉션 후 최종 주소 포함)의 등록 도메인과 비교해
`printed_domain_check`(`matched`/`mismatched`/`not_checked`)를 반환합니다. 진짜 안내문 위에 가짜 QR 스티커를 덧붙인 경우를 잡기 위한 신호입니다.
불일치는 종합 판정에 PRINTED_DOMAIN_MISMATCH(25점, 단독으로 주의)로 반영합니다. 주문·예약 대행 서비스처럼 정상적으로 다른 경우도 있어 위험이 아닌 주의로 둡니다.
설명 AI에는 상태(printed_domain_status)만 보내고 인쇄된 주소 자체는 보내지 않습니다. 구현: `app/services/printed_domain.py`, 테스트: `tests/test_printed_domain.py`.
- 후보는 최대 5개·각 30자 이하이고, 공식 도메인 DB에 있는 이름(registered=true)이 앞에 옵니다. 앱은 후보를 보여주기만 하고, 사용자가 고른 이름만 brand_texts로 보냅니다.
- 사진 속 글자가 지시문이어도 따르지 않도록 프롬프트에 명시하고, 응답은 JSON 형식·길이·URL 포함 여부로 검증합니다.
- 기본 모델은 BAZE_MODEL이며, 다른 이미지 모델을 쓰려면 `.env`에 `BAZE_VISION_MODEL`을 지정합니다.
- 사진 한 장당 유료 AI 호출 1회가 발생합니다.

URL 검사 요청은 `qr_text`, 선택적인 `brand_texts`, `store_id`를 받습니다.
`/api/url/analyze`는 기본적으로 외부 요청 없이 패턴·매장 검사를 하며 공식 도메인은 확인 불가입니다.
`include_ai=true`이면 검색 제공자를 통해 공식 도메인을 확인합니다. 이 API 자체는 점수를 산정하지 않습니다.
`risk_signals`를 기존 `behavior-v1` 점수에 자동으로 합산하지 않습니다.
`/api/analyze`는 서버 내부에서 같은 `analyze_url_signals()` 공통 함수를 호출합니다.
`/api/url/analyze`는 URL 검사만 필요한 경우에 사용하며 서버가 자기 API를 HTTP로 호출하지 않습니다.
상세 명세는 [위험 신호 데이터 명세](app/docs/risk_signals_contract.md)를 참고하세요.

## API

POST /api/analyze

```json
{
  "qr_text": "https://example.com",
  "brand_texts": [],
  "store_id": null,
  "include_ai": true,
  "inspect_page": true,
  "include_explanation": true
}
```

qr_text와 brand_texts는 필수입니다. brand_texts는 공식 도메인 비교에 사용하며 인식한 브랜드가 없으면 []를 보냅니다.
store_id는 선택 항목이며 매장 검색 결과의 ID를 보냅니다. 생략/null이면 매장 비교는 not_checked입니다.
QR URL은 최대 4,096자, 브랜드명은 최대 30개, store_id는 최대 128자입니다.
기본 URL 검증과 로컬 URL 검사가 통과한 뒤 DNS·페이지 수집·AI 호출을 진행합니다.
include_ai 기본값 true, inspect_page 기본값 false.
본문 분석에는 inspect_page=true가 필요합니다.
inspect_page=false이면 대상 페이지의 HTTP 요청과 유료 AI 행동 분류 호출을 하지 않습니다.
include_explanation 기본값 false. true이고 include_ai=true이면 완성된 검사 결과를 쉬운 문장으로 설명하는 AI 호출을 1회 추가합니다(10분 캐시).
설명 AI에는 점수·등급·근거 코드·검사 상태·URL 신호 코드만 보내며 URL·호스트명·상표명·매장명은 보내지 않습니다. 설명은 점수와 등급을 바꾸지 않습니다.
include_ai=false이면 페이지 수집을 요청해도 AI 행동 점수를 산출하지 않습니다.
잘못된 스킴/사용자 정보/80·443 외 포트/입력 형식은 422를 반환합니다.

## 통합 응답의 URL 검사 결과

- `url_analysis`: 입력 URL의 패턴·브랜드·매장 검사 상세와 `risk_signals`.
- `final_url_analysis`: 페이지 수집이 성공했고 최종 URL이 바뀐 경우 그 주소의 같은 검사 결과. 이외에는 null.
- `suspicious_patterns.codes`와 `risk_signals.pattern_codes`: 사람이 읽는 문구와 독립적인 위험 신호 코드.
- `IP_LITERAL`, `SHORT_URL`, `EXECUTABLE_LINK`, `EXECUTABLE_QUERY`, `USERINFO_IN_URL` 코드를 사용합니다.
- 통합 API는 사용자 정보가 포함된 URL을 422로 거부합니다. 개별 URL 검사 API는 USERINFO_IN_URL 신호로 보고할 수 있습니다.
- URL 검사 status=ok는 처리 성공일 뿐 안전 판정이 아닙니다.
- 로컬 DB 읽기/해석 실패 시 해당 검사는 unknown, URL 검사 status는 partial, errors에는 실패 코드가 반환됩니다.
- store_data_verified=null은 매장 검사 미수행/조회 실패, false는 조회된 검증 상태가 미검증임을 뜻합니다.
- 최종 주소의 URL 검사는 추가 HTTP/AI 요청을 하지 않으며 입력 주소와 최종 주소의 신호를 중복 가산하지 않습니다.

## combined-v1 종합 판정 (`verdict`)

결과 화면 배너와 AI 결과 설명은 응답의 `verdict`를 따릅니다. 기존 `score`/`level`(behavior-v1)은 바꾸지 않고 그대로 반환합니다.
구현: `app/verdict.py`, 테스트: `tests/test_verdict.py`. 공식 도메인·사칭 근거는 현재 `app/domain_ai.py`의 AI 검색 판정을 사용합니다.

종합 점수 = behavior-v1 구성 점수(AI 행동 ≤60 + TLS ≤25 + 도메인 생성일 ≤15) + 아래 URL 신호 점수, 최대 100.

| 코드                       | 점수 | 조건                                                                                  |
| -------------------------- | ---- | ------------------------------------------------------------------------------------- |
| BLOCKED_NAVIGATION         | 50   | navigation_allowed=false (내부망 주소, HTTPS→HTTP 이동 등). 점수와 상관없이 항상 위험 |
| EXECUTABLE_DOWNLOAD        | 50   | EXECUTABLE_LINK/EXECUTABLE_QUERY 또는 page.download_response                          |
| BRAND_DOMAIN_MISMATCH      | 50   | AI 검색 근거가 있는 사칭 의심(brand_domain_status=mismatched)                                                        |
| STORE_DOMAIN_IMPERSONATION | 50   | domain_impersonation_status=impersonation_suspected                                   |
| STORE_QR_MISMATCH          | 25   | store_qr_status=mismatched (위장 도메인으로 이미 잡히면 중복 가산 안 함)              |
| PRINTED_DOMAIN_MISMATCH    | 25   | printed_domain_check.status=mismatched (QR 주변 인쇄 주소와 QR 주소가 다름)          |
| SHORT_URL                  | 20   | 단축 URL                                                                              |
| IP_LITERAL                 | 20   | IP 주소형 URL                                                                         |
| REDIRECT_PARAMETER         | 20   | redirect_pattern_detected=true                                                        |
| BRAND_IN_DOMAIN            | 50   | 공식 도메인 DB의 상표 단어(naver, starbucks 등)가 공식이 아닌 도메인에 포함 (입력 상표·매장 사칭으로 이미 잡히면 중복 가산 안 함) |
| PHISHING_KEYWORD_DOMAIN    | 20   | 등록 도메인 이름에 login·verify·secure·refund·delivery 등 낚시성 단어                 |

`domain_keyword_check`(`app/services/domain_keywords.py`, 테스트 `tests/test_domain_keywords.py`)
- `brand_in_domain`: 상표 단어는 공식 도메인 DB에서 가져옵니다(`naver.com` → `naver`, 4글자 이상, 데모 항목 제외). 그 상표의 공식 도메인과 하위 도메인은 제외합니다.
- 오타·비슷한 글자로 흉내 낸 도메인(`nav3r.com`, `starbuks.co.kr`, `edlya.com`)도 `brand_in_domain`(`match: lookalike`)으로 잡습니다.
  3↔e, 0↔o, 1·i↔l, rn↔m 등 헷갈리는 글자를 같게 본 뒤, 8글자 이상 상표는 2글자까지, 짧은 상표는 글자 순서 바뀜·1글자 추가/누락만 허용합니다
  (짧은 상표에서 다른 글자로 바꾼 경우는 never·saver 같은 일반 단어와 겹쳐 제외). 5글자 미만 상표는 비교하지 않습니다.
- `domain_keywords`: 등록 도메인 이름(`secure-login-verify.com`)에 있을 때만 점수에 반영합니다.
- `path_keywords`: 하위 도메인·경로·쿼리(`login.example.org/account`)의 단어는 정상 사이트에도 흔해 참고로만 반환합니다.
- 설명 AI에는 해당 여부만 보내고 단어·도메인 자체는 보내지 않습니다.

- HTTP QR 분석에서 상표 사칭은 AI 검색 출처로 판단합니다. 위의 로컬 도메인 단어·오타 함수 설명은 레거시 오프라인 검사에 해당하며, 현재 HTTP 경로는 고정 상표 DB를 읽지 않습니다.
- 입력 주소와 최종 이동 주소의 신호는 합쳐서 신호마다 한 번만 더합니다.
- 50 이상 위험, 20~49 주의, 20 미만은 `verdict.assessment_status=complete`일 때만 낮음, 그 외 확인 불가.
- `verdict.assessment_status`는 behavior-v1 검사 완료 여부와 입력·최종 URL 검사 성공 여부를 함께 반영합니다. 요청한 상표 비교의 결과가 unknown이거나 DB 조회가 실패하면 미완료입니다. 상표를 입력하지 않아 비교하지 않은 경우는 선택 검사 생략입니다.
- unknown·조회 실패는 악성 근거가 아니므로 임의의 벌점을 추가하지 않습니다. 0점도 미완료라면 안전 판정이 아닙니다. 모든 점수 항목이 미측정이면 score=null입니다.
- AI 네 유형이 각각 한 번씩 평가되어야 완료입니다. 빈 배열·중복·누락·unknown 또는 읽지 못한 페이지는 정상 판정으로 처리하지 않습니다.
- `m.site.naver.com`(네이버 QR 중계)과 `naver.me`도 SHORT_URL 20점에 포함합니다. 정상 서비스라도 목적지를 숨기는 구조에 대한 주의이며 악성 확률 20%라는 뜻은 아닙니다.
- 프론트는 검사 실패를 ‘확인 불가’, 선택 검사 생략을 ‘미검사’, 조사 범위에서 신호가 없으면 ‘신호 미발견’, 인증서·생성일 등 조회 성공은 ‘확인됨’으로 구분합니다. 미완료 점수에는 ‘확인된 위험 점수’와 누락 항목을 표시합니다.
- 배점 기준: 그 신호 하나만으로 접속을 말려야 하는 경우(다운로드·사칭·차단)는 단독으로 위험(50), 목적지를 숨기는 신호는 단독으로 주의(20).
- 해외 IP는 behavior-v1과 같이 0점(정보만 표시)입니다.
- 이 배점값은 `SIGNAL_POINTS` 한 곳에서 바꿉니다.

## behavior-v1 점수

AI는 네 가지 공격 유형을 none/weak/moderate/strong/unknown으로 분류합니다.

- credential_theft: 인증정보 탈취
- personal_data_theft: 개인정보 탈취
- financial_fraud: 금전 피해 유도
- unsafe_installation: 위험한 설치 유도

서버가 위험 수준을 0/10/30/60점으로 변환합니다. unknown은 0이 아니라 null입니다.
AI 점수는 유형별 최고값 하나만 사용합니다. 중복되는 공격 유형을 합산하지 않습니다.
AI가 직접 숫자 점수를 정하거나 입력된 지시문으로 점수를 변경할 수 없습니다.
모든 긍정 판단은 실제 수집한 근거 ID를 참조해야 합니다.
moderate/strong은 입력란·설치 링크만으로 인정하지 않고 본문의 요구 행동 근거가 필요합니다.
strong은 긴급성/위협/보상/복구 문구 요구/보안 해제 같은 추가 문맥을 요구합니다.
일반 로그인/외부 SSO/결제/정상 다운로드/피싱 설명문을 공격으로 단정하지 않도록 지시합니다.
현재 근거 검증용 어휘는 한국어·영어 중심입니다. 오탐/미탐 가능성이 있어 평가 데이터로 보정해야 합니다.

최종 점수 = AI 행동 분석(최대 60) + TLS(최대 25) + 도메인 생성일(최대 15).

- 인증서 검증 실패: 25
- HTTP: 10 (TLS 항목 내 중복 합산 없음)
- 도메인 생성 30일 미만: 15
- 30~179일: 5
- 해외 IP: 0, 국가 정보만 반환
- IP 주소형/단축 URL/실행 파일 확장자/브랜드 불일치: 이 버전의 점수에서 제외(2번 범위)
  최종 이동 호스트가 바뀌면 원본과 최종 TLS·생성일 중 더 높은 값을 한 번만 사용합니다.

주요 응답:

```json
{
  "score": 75,
  "score_version": "behavior-v1",
  "score_scope": "ai_behavior_tls_domain_age",
  "assessment_status": "complete",
  "components": { "ai_behavior": 60, "tls": 0, "domain_age": 15 },
  "attack_types": [
    {
      "type": "credential_theft",
      "severity": "strong",
      "evidence_ids": ["page_text_1"]
    },
    { "type": "personal_data_theft", "severity": "none", "evidence_ids": [] },
    { "type": "financial_fraud", "severity": "none", "evidence_ids": [] },
    { "type": "unsafe_installation", "severity": "none", "evidence_ids": [] }
  ]
}
```

이 예시는 전체 응답의 일부입니다. evidence/reasons/level/auto_open과 url_analysis/final_url_analysis도 함께 반환합니다.
score_scope=ai_behavior_tls_domain_age: 점수와 level/assessment_status는 기존 AI 행동·TLS·도메인 생성일 범위만 나타냅니다.
URL·브랜드·매장 신호는 반환하지만 이 점수에는 가산/감산하지 않습니다. URL의 종합 안전 점수로 해석하지 마세요.
0점/낮음이더라도 url_analysis와 final_url_analysis의 위험 신호 및 조회 상태를 함께 확인해야 합니다.
URL 신호를 점수에 포함하는 배점·중복 처리 규칙은 별도 점수 버전(아래 combined-v1)에서 적용합니다.
page.evidence에는 근거 ID·종류·정제된 텍스트가 있습니다. HTML로 렌더링하지 말고 텍스트로 취급하세요.
reasons에는 합계에 기여한 항목과 points/evidence_ids가 반환됩니다.
ai_status는 행동 분류 처리 상태입니다. ai_explanation은 호환성을 위한 서버 요약이며 별도 AI 호출이 아닙니다.
explanation은 결과 화면용 설명입니다. explanation_status가 generated/cached이면 AI가 쓴 문장이고, 그 외(disabled/unavailable/skipped)에는 ai_explanation과 같은 규칙 기반 문장입니다.
navigation_allowed=false(내부망 차단·HTTPS→HTTP 이동 등)이면 설명 AI를 호출하지 않습니다(explanation_status=skipped).
이때 explanation_skip_reason에 AI 설명을 만들지 않은 이유(차단 사유)를 사용자용 문장으로 반환하며, 결과 화면의 AI 설명 칸에 표시합니다.
AI 키 미설정·시간 초과·잘못된 응답(explanation_status=unavailable)에도 explanation_skip_reason에 안내 문장을 반환합니다.
include_explanation=false(disabled)이면 null입니다.

AI 설명 출력 필터(`app/ai.py`의 `explanation_problems`): AI 문장이 아래 규칙을 어기면 화면에 보내지 않고 캐시하지 않으며,
explanation_status=unavailable과 안내 문장으로 대신합니다.
- INTERNAL_WORDING: 사용자·자동 접속·시스템·서버 같은 내부 표현
- GRADE_OR_SCORE: 등급·확인 불가·점수·"N점"
- TECH_TERM: DNS·TLS·RDAP·GeoIP 같은 기술 용어, SHORT_URL·brand_domain_status 같은 코드 이름
- FORMAL_ENDING: "~습니다/~니다" 합쇼체
- LINK_OR_MARKDOWN: 링크·마크다운·목록 기호
- RECHECK_CONFIRMED: 공식 도메인이 일치했는데 "공식 사이트인지 확인"·"공식 앱이나 직접 검색"을 권하는 문장

프롬프트를 바꾼 뒤에는 정해진 사례로 설명 문장을 확인하세요. 사례는 `tests/fixtures/explanation_cases.json`입니다.
```powershell
.\.venv\Scripts\python.exe -B -m scripts.check_explanations            # 사례 목록만 (요청 없음)
.\.venv\Scripts\python.exe -B -m scripts.check_explanations --live --repeat 2
.\.venv\Scripts\python.exe -B -m scripts.check_explanations --live --case naver_brand --repeat 3
```
--live는 실제 사이트 조회와 유료 AI 호출(사례마다 페이지 분석 1회 + 설명 repeat회)을 합니다. 필터 적용 전 원문과 어긴 규칙,
종합 판정이 기대 등급과 같은지를 보여줍니다. 판정은 외부 조회 결과에 따라 실행마다 달라질 수 있습니다.

TLS 검증은 OS 인증서 저장소 대신 certifi(Mozilla) CA 묶음을 사용합니다. Windows에서 루트 인증서가 아직 내려받아지지 않아
정상 사이트(example.com, bit.ly 등)가 INVALID_TLS(+25)로 잘못 채점되던 문제를 막기 위함입니다.

- complete: behavior-v1 메타데이터와 네 가지 행동 유형의 정적 검사 완료
- partial: 산출한 항목의 점수만 반환. AI 미사용/실패/unknown, 조회 누락, meta refresh 등이 해당
- failed: 산출 가능한 항목이 없어 score=null. 내부 DNS 차단도 이 상태로 반환 가능
- null인 구성 점수는 미평가이며 0점과 다릅니다.
- 50 이상 위험, 20~49 주의. 20 미만은 complete일 때만 낮음, 이외에는 확인 불가.
- evidence_complete는 메타데이터 조회 완료 여부, analysis_complete는 behavior-v1 검사 완료 여부. URL 검사의 status와는 별개입니다.
  검사 완료는 정적 검사 범위의 완료를 뜻하며 실제 안전이나 악성 확률을 보증하지 않습니다.
  score/assessment_status/components는 기존 버전과 계약이 달라졌으므로 프론트도 함께 맞추세요.

## 페이지 수집 보호

- HTTP(S)·80/443만, 사용자 정보/내부·예약 IP/혼합 DNS 차단.
- 이동마다 DNS 전체를 재검증하고, 검증한 공인 IP에 연결을 고정.
- 원래 hostname으로 Host/SNI/인증서 검증, HTTPS→HTTP 이동 차단.
- 쿠키/로그인 세션/사용자 인증 헤더/환경 프록시 미사용. BAZE 키는 대상 사이트에 전송하지 않음.
- HTTP 리디렉션 최대 3회, 전체 수집 18초, HTML 최대 256KiB.
- 비 HTML/첨부/압축 응답 및 알려진 파일 경로는 본문 검사 중단.
- JavaScript 실행, iframe/하위 리소스 요청, 폼 제출, 파일 실행 없음.
- HTML/JS 기반 이동은 따라가지 않으며 meta refresh는 검사 미완료로 표시.
- 최대 4,000자 본문과 제한된 폼 관찰 결과를 BAZE에 전달. 입력값/숨겨진 폼 값은 수집하지 않음.
- URL/이메일/긴 숫자열은 제거하나 개인정보를 완벽하게 제거하는 기능은 아님.
- 수집 HTML은 디스크에 저장하지 않음. 유효한 AI 분류는 10분간 최대 128개 캐시.
- AI 응답은 JSON 스키마·공격 유형·위험 수준·실제 근거 참조와 지지 어휘로 검증.
  AI 실패/잘린 응답/없는 근거/부적절한 분류는 사용하지 않고 메타데이터 부분 점수를 반환합니다.
  추가 설명용 유료 호출이나 유료 자동 재시도는 하지 않습니다.

서버가 제한된 HTTP 요청을 보내는 방식이며 별도 VM/컨테이너 샌드박스는 아닙니다.
공개 운영 전 수집 워커 네트워크 격리·송신 제한·API 인증·요청 제한을 적용하세요.
휴대폰의 보호는 프론트가 스캔 시 URL 자동 열기/WebView 로딩을 하지 않는다는 전제가 필요합니다.
사용자가 직접 사이트에 접속한 이후의 동작은 보호 범위가 아닙니다.
브랜드 도메인 대조는 로컬 등록 DB를 사용하며 외부 기관을 통한 공식성 검증은 아닙니다.
알려진 악성 URL DB, 동적 페이지/실행 파일 분석은 포함하지 않습니다.

## Expo와 개발 네트워크

프론트 .env에는 PC Wi-Fi IPv4 주소를 넣습니다.

```dotenv
EXPO_PUBLIC_API_URL=http://192.168.0.10:8000
```

휴대폰의 localhost는 PC가 아닙니다. PC/휴대폰을 같은 신뢰할 수 있는 Wi-Fi에 연결하세요.
먼저 휴대폰 브라우저에서 http://PC_IP:8000/health 를 확인합니다.
CORS_ORIGINS는 Expo Web의 실제 origin을 지정하는 설정입니다.

관리자 PowerShell에서 개발용 규칙 생성:

```powershell
New-NetFirewallRule -DisplayName "QRAlert FastAPI 8000" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 -Profile Private -RemoteAddress LocalSubnet
```

이미 있는 규칙 수정:

```powershell
Set-NetFirewallRule -DisplayName "QRAlert FastAPI 8000" -Profile Private -RemoteAddress LocalSubnet
```

종료 시 서버 Ctrl+C, 개발용 규칙 제거:

```powershell
Remove-NetFirewallRule -DisplayName "QRAlert FastAPI 8000"
```

LocalSubnet은 로컬 서브넷 범위이며 휴대폰 한 대만 뜻하지 않습니다. 실제 배포에는 HTTPS 서버를 사용하세요.

## 검증

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m unittest discover -s app/tests -v
```

자동 테스트는 외부 네트워크·유료 API를 모의 응답으로 대체합니다.
실제 모델 결과는 변경될 수 있으며, 테스트 통과 횟수는 탐지 정확도를 뜻하지 않습니다.
평가 시 정상 로그인/SSO/다운로드/결제 및 공격·지시문 삽입 사례를 별도로 검증하세요.

## 직접 구별 성능 평가하기

외부 사이트 없이 정답이 있는 정적 HTML 예제 10개(정상 6개·위험 4개)를 평가할 수 있습니다.
예제는 `tests/fixtures/behavior_cases.json`, 실행 코드는 `scripts/evaluate_behavior.py`에 있습니다.
기본 명령은 목록만 보여주고 외부 요청을 하지 않습니다. 서버를 켤 필요가 없습니다.

```powershell
.\.venv\Scripts\python.exe -B -m scripts.evaluate_behavior
```

실제 `.env`의 BAZE 모델로 평가하려면 다음 명령을 실행합니다. 선택한 사례마다 AI 호출이 발생하며 토큰을 사용합니다.

```powershell
.\.venv\Scripts\python.exe -B -m scripts.evaluate_behavior --live
```

특정 정상·위험 사례만 비교해 호출 수를 줄일 수 있습니다.

```powershell
.\.venv\Scripts\python.exe -B -m scripts.evaluate_behavior --live --case normal_login --case credential_phishing
```

- `PASS`: 정상 예제에서 네 유형 모두 none이거나, 위험 예제의 지정 공격 유형이 moderate 이상으로 판정됨.
- `FAIL`: 정상 예제의 오탐, 위험 예제의 미탐·잘못된 유형·강도 부족. 실제 결과를 보고 사례 내용을 함께 검토하세요.
- `INCONCLUSIVE`: API 실패·unknown 등으로 충분히 평가하지 못함. 정상 판정이나 성공으로 세지 않습니다.
- `ai_points`: AI 행동 점수(최대 60)만 표시하며 TLS·도메인·URL 패턴 점수는 포함하지 않습니다.
- `summary.confusion`: TP=위험에서 경고, TN=정상에서 경고 없음, FP=정상인데 경고, FN=위험인데 경고 없음.
  이 통계는 weak 이상을 경고로 세며, PASS는 지정 공격 유형이 moderate 이상이어야 하므로 TP여도 FAIL일 수 있습니다.
- `coverage`: 전체 중 네 공격 유형을 모두 평가한 비율. 실패·미확인을 제외한 수치만으로 성능을 과장하지 마세요.

이 명령은 HTML을 분석할 뿐 웹페이지 접속, JavaScript 실행, 폼 제출, 파일 다운로드를 하지 않습니다.
본인이 만든 새 예제는 JSON에 고유 id, label(benign/malicious), html을 추가하세요.
malicious 예제에는 expected_attack(credential_theft/personal_data_theft/financial_fraud/unsafe_installation)이 필요합니다.
--cases 경로로 별도의 평가 파일도 사용할 수 있습니다. HTML의 정제된 내용이 BAZE에 전달되므로 개인정보·비밀키는 넣지 마세요.
현재 예제는 작은 기능 확인용 세트이며 실제 사이트 탐지 정확도의 추정치가 아닙니다.
모델은 비결정적일 수 있으므로 실패 사례를 유지하고 표현·언어·정상 서비스 사례를 다양하게 확장하세요.

## Swagger로 URL 연동 확인하기

1. 위 실행 명령으로 백엔드를 켜고 http://127.0.0.1:8000/docs 에 접속합니다.
2. POST /api/analyze에서 Try it out을 누른 뒤 위 API 예제의 URL을 https://www.python.org로 바꾸어 실행합니다.
3. inspect_page=true, include_ai=true일 때 page.status와 ai_status, score/components/reasons, url_analysis를 확인합니다.
4. include_ai=false로 다시 실행하면 ai_behavior=null이어야 합니다. 이 경우 0점/partial도 안전 판정이 아닙니다.
5. URL 패턴만 검사하려면 POST /api/url/analyze를 사용합니다. 이 경로는 대상 사이트·AI에 접속하지 않습니다.

URL 검사 예제:

| 입력                                                                             | 기대 관찰                                   |
| -------------------------------------------------------------------------------- | ------------------------------------------- |
| https://bit.ly/demo                                                              | SHORT_URL                                   |
| https://example.com/setup.apk                                                    | EXECUTABLE_LINK                             |
| https://example.com/download?file=setup%252Eapk                                  | EXECUTABLE_QUERY                            |
| https://menu.example.com/store/demo-cafe-01?table=3 + store_id=demo-cafe-01      | matched, store_data_verified=false(데모 DB) |
| https://menu.example.com.evil.example/store/demo-cafe-01 + store_id=demo-cafe-01 | 위장 도메인 의심                            |

통합 API에서 https://127.0.0.1은 내부 주소 차단, not-a-url은 422가 기대 결과입니다.
2번의 URL 신호는 behavior-v1 점수와 별도이므로 실행 파일 링크가 잡혀도 점수가 반드시 올라가지는 않습니다.
AI의 내용 구별은 위 정답 예제 평가로, 실제 수집과 API 연결은 Swagger로 나누어 확인하세요.

## 사진에서 상표명 OCR

`POST /api/ocr/brands/local`에 JPEG/PNG 사진을 multipart 파일 필드 `image`로 보내면,
한국어·영어 글자와 등록된 브랜드 후보를 반환합니다. 후보를 확인한 뒤 기존 `/api/analyze`에 brand_texts로 전달하세요.

- EasyOCR CPU 실행, 별도 OCR API 키·BAZE 호출 없음.
- 최대 5MiB·1,600만 화소, 방향 보정 및 긴 변 1,600픽셀 축소.
- 낮은 신뢰도·여러 브랜드·미등록 브랜드를 구분하며, 인식 결과는 자동 확정하지 않음.
- OCR 모델은 한 번 준비하고 재사용. 일반 요청에서는 모델 다운로드를 하지 않음.
- 기본 requirements에 더해 requirements-ocr.txt 설치와 모델 준비가 필요함.

```powershell
.\.venv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements-ocr.txt
.\.venv\Scripts\python.exe -B -m scripts.setup_ocr --download-models
```

서버를 켠 뒤 `/docs`에서 파일 업로드로 테스트하거나 다음 명령으로 사진을 직접 검사할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe -B -m scripts.check_ocr "C:/Users/User/Desktop/brand.jpg"
```

[OCR 요청·응답과 프론트 연결 방법](app/docs/ocr_api.md)에 설치, 상태 코드, 브랜드 별칭 추가 방법을 정리했습니다.

## 단축 링크 해제 후 2번 검사

POST /api/url/analyze에 `resolve_redirects: true`를 추가하면, 서버가 HTTP 이동을 확인한 뒤
최종 주소의 URL 패턴·브랜드·매장 검사 결과를 `final_url_analysis`로 함께 반환합니다.
기본값 false에서는 기존의 로컬 검사 동작을 유지합니다. AI 호출은 사용하지 않습니다.
요청 예시와 상태·제한은 [단축 링크 연결 명세](app/docs/url_resolution.md)를 참고하세요.
