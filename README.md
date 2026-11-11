# QR Alert FastAPI backend

이 저장소는 QR의 HTTP(S) URL을 받아 서버에서 도메인·TLS·IP 국가 정보를 조회하고,
선택적으로 정적 HTML과 AI를 이용해 요구 행동의 위험도를 평가합니다.
휴대폰 앱은 URL을 보내고 JSON을 받습니다. 1번의 QR/OCR, 2번의 URL 패턴·브랜드 비교,
4번의 결과 화면과 사용자 확인 후 URL 열기는 별도 담당 범위입니다.

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
키·.env·국가 DB는 Git에 포함되지 않습니다. Expo의 EXPO_PUBLIC_*에 AI 키를 넣지 마세요.
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

| 경로 | 기능 |
| --- | --- |
| `POST /api/analyze` | 기존 도메인·TLS·국가 정보 및 선택적 AI 행동 점수 |
| `POST /api/url/analyze` | URL 패턴·브랜드·매장 QR 비교 및 `risk_signals` |
| `GET /api/stores/search?keyword=테스트카페` | 등록된 매장 이름 검색 |

URL 검사 요청은 `qr_text`, 선택적인 `brand_texts`, `store_id`를 받습니다.
이 검사는 대상 사이트에 접속하지 않으며 점수를 산정하지 않습니다.
`risk_signals`를 기존 `behavior-v1` 점수에 자동으로 합산하지 않습니다.
서로 다른 요청·응답 형식을 유지하기 위해 분석 경로를 분리했습니다.
상세 명세는 [위험 신호 데이터 명세](app/docs/risk_signals_contract.md)를 참고하세요.

## API
POST /api/analyze
```json
{
  "qr_text": "https://example.com",
  "brand_texts": [],
  "include_ai": true,
  "inspect_page": true
}
```
qr_text와 brand_texts는 필수입니다. brand_texts는 현재 분석에 반영하지 않습니다.
include_ai 기본값 true, inspect_page 기본값 false.
본문 분석에는 inspect_page=true가 필요합니다.
inspect_page=false이면 대상 페이지의 HTTP 요청과 유료 AI 호출을 하지 않습니다.
include_ai=false이면 페이지 수집을 요청해도 AI 행동 점수를 산출하지 않습니다.
잘못된 스킴/사용자 정보/80·443 외 포트/입력 형식은 422를 반환합니다.

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
  "assessment_status": "complete",
  "components": {"ai_behavior": 60, "tls": 0, "domain_age": 15},
  "attack_types": [
    {"type": "credential_theft", "severity": "strong", "evidence_ids": ["page_text_1"]},
    {"type": "personal_data_theft", "severity": "none", "evidence_ids": []},
    {"type": "financial_fraud", "severity": "none", "evidence_ids": []},
    {"type": "unsafe_installation", "severity": "none", "evidence_ids": []}
  ]
}
```
이 예시는 전체 응답의 일부입니다. 기존 evidence/reasons/level/auto_open 등도 함께 반환합니다.
page.evidence에는 근거 ID·종류·정제된 텍스트가 있습니다. HTML로 렌더링하지 말고 텍스트로 취급하세요.
reasons에는 합계에 기여한 항목과 points/evidence_ids가 반환됩니다.
ai_status는 행동 분류 처리 상태입니다. ai_explanation은 호환성을 위한 서버 요약이며 별도 AI 호출이 아닙니다.

- complete: 메타데이터와 네 가지 행동 유형의 정적 검사 완료
- partial: 산출한 항목의 점수만 반환. AI 미사용/실패/unknown, 조회 누락, meta refresh 등이 해당
- failed: 산출 가능한 항목이 없어 score=null. 내부 DNS 차단도 이 상태로 반환 가능
- null인 구성 점수는 미평가이며 0점과 다릅니다.
- 50 이상 위험, 20~49 주의. 20 미만은 complete일 때만 낮음, 이외에는 확인 불가.
- evidence_complete는 메타데이터 조회 완료 여부, analysis_complete는 전체 검사 완료 여부.
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
알려진 악성 URL DB, 동적 페이지/실행 파일 분석, 공식 도메인 대조는 포함하지 않습니다.

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
```
자동 테스트는 외부 네트워크·유료 API를 모의 응답으로 대체합니다.
실제 모델 결과는 변경될 수 있으며, 테스트 통과 횟수는 탐지 정확도를 뜻하지 않습니다.
평가 시 정상 로그인/SSO/다운로드/결제 및 공격·지시문 삽입 사례를 별도로 검증하세요.
