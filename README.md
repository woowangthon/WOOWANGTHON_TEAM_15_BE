# QR Alert FastAPI backend

## 담당 범위와 구현 순서
1. 1번 담당(Expo): 카메라/이미지에서 QR 문자열 추출. URL 자동 이동 금지.
2. 2번 담당: URL 패턴·브랜드 비교. 현재 brand_texts는 호환용 입력이며 비교하지 않음.
3. 이 저장소(3번 담당): 입력 검증 → DNS 공인 IP 확인 → RDAP 생성일/TLS 인증서 병렬 조회 → IP 국가 조회 → 점수/근거 반환.
4. 4번 담당: 결과 화면, 선택적인 AI 설명, 사용자 확인 후 이동.

이미지 업로드, OCR, DB 분석 이력 영구 저장은 현재 범위에 포함되지 않습니다. 선택적 페이지 검사에서는 검증된 HTTP 리디렉션을 제한적으로 추적합니다.
검사 결과와 근거는 JSON 응답으로 반환하며 서버에 영구 저장하지 않습니다.

## 실행 (Python 3.11 이상)
저장소 루트 PowerShell:
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
PC 문서: http://127.0.0.1:8000/docs
상태 확인: GET /health

서버 시작 시 저장소 루트의 .env를 자동으로 읽습니다. 이미 설정된 PowerShell/배포 환경 변수가 우선합니다.
선택 설정:
```powershell
$env:GEOIP_DB_PATH = "C:\data\GeoLite2-Country.mmdb"
$env:CORS_ORIGINS = "http://localhost:8081"
```
GeoLite2 Country DB는 MaxMind에서 이용 조건에 맞게 별도 확보하고 주기적으로 갱신하세요.
DB가 없으면 국가 조회는 unknown이며 다른 검사는 계속합니다.
국가는 서버 IP의 위치 추정치이며 운영자 국적이 아닙니다. 해외라는 이유만으로 점수를 부여하지 않습니다.
CORS는 Expo Web에서 필요한 경우 실제 웹 origin을 지정합니다. 네이티브 앱 통신 문제를 방화벽 대신 해결하는 설정이 아닙니다.

## API 계약
POST /api/analyze
```json
{"qr_text":"https://example.com","brand_texts":[]}
```
두 필드 모두 필수. URL 길이 최대 4096. 잘못된 URL/미지원 스킴/사용자 정보/비표준 포트는 422.
응답: url, hostname, evidence(dns/rdap/tls/geoip), score, level, reasons,
analysis_complete, navigation_allowed, auto_open(false), requires_confirmation(true), warning.
외부 조회 실패는 HTTP 200과 해당 evidence.status=unknown으로 표현합니다.
내부/예약 주소 및 공인·내부 혼합 DNS는 blocked, navigation_allowed=false.
analysis_complete는 외부 조회의 완료 여부이며 전체 보안 검사의 완전성이나 안전 보증이 아닙니다.

점수는 악성 확률이 아닌 초기 휴리스틱입니다. 실제 데이터로 조정해야 합니다.
- HTTP: 15
- IP 주소형: 15
- 알려진 단축 URL: 20 (페이지 검사 모드는 목적지를 제한적으로 추적)
- 실행/설치 파일 경로: 35 (실제 응답/파일 확인 안 함)
- 도메인 생성 30일 미만: 25 / 180일 미만: 10 (중복 없음)
- TLS 인증서 검증 실패: 25
합계 최대 100. 50 이상 위험, 20 이상 주의.
20 미만이고 누락된 조회가 있으면 확인 불가, 모두 완료되면 낮음.
HTTPS와 오래된 도메인도 안전을 보장하지 않습니다.

## 외부 조회와 안전 경계
RDAP: IANA HTTPS bootstrap → 등록 도메인 RDAP. tldextract 내장 Public Suffix List 사용.
RDAP redirect는 자동 추적하지 않아 일부 등록기관은 unknown일 수 있습니다.
TLS: DNS에서 얻은 공인 IP에 직접 연결하고 원래 호스트명으로 SNI/인증서 검증.
인증서 만료·호스트명·신뢰 체인을 검사합니다. DNS IP 중 첫 번째 IP만 검사합니다.
기본 모드에서는 대상 URL의 HTTP 요청이나 단축 URL 이동을 하지 않습니다. inspect_page=true는 아래 제한된 GET 수집을 수행합니다.
DNS/TLS 연결은 발생하므로 대상 서버와 전혀 통신하지 않는 방식은 아닙니다.
조회별 timeout 적용, RDAP 전체 12초 제한. DB 미설정/네트워크 실패를 안전으로 간주하지 않습니다.
운영 배포 전 인증/요청 제한, 동시 요청 상한, 외부 조회 캐시, 최신 PSL/국가 DB,
외부 송신 네트워크 정책을 추가해야 합니다. 현재는 개발용 MVP입니다.

## Expo 별도 저장소 연동
프론트 .env:
```dotenv
EXPO_PUBLIC_API_URL=http://192.168.0.10:8000
```
192.168.0.10은 예시. PC의 ipconfig에서 Wi-Fi IPv4 주소를 확인해 교체하세요.
휴대폰의 localhost는 휴대폰 자신이므로 PC 주소를 사용합니다.
휴대폰/PC를 같은 신뢰할 수 있는 Wi-Fi에 연결하세요. AP 기기 간 통신 차단이 있으면 접속되지 않을 수 있습니다.

```typescript
const response = await fetch(process.env.EXPO_PUBLIC_API_URL + "/api/analyze", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ qr_text: scannedText, brand_texts: [] }),
});
if (!response.ok) throw new Error("URL 분석 요청 실패");
const result = await response.json();
// 결과 화면에 result.url / level / score / reasons / evidence 표시.
// 스캔 콜백에서는 Linking.openURL을 호출하지 않습니다.
// 사용자가 '그래도 접속'을 누른 뒤 확인 대화상자에서 동의할 때만:
// if (result.navigation_allowed) await Linking.openURL(result.url);
```
실제 앱에서는 중복 스캔 잠금, 로딩/오류 표시, 확인 대화상자를 구현하세요.
EXPO_PUBLIC_*는 앱에 공개되므로 AI API 키를 넣지 마세요.

## 사진의 Windows 방화벽 설정
방화벽 규칙은 같은 네트워크의 휴대폰이 PC의 8000번 포트에 들어오도록 하는 개발 설정입니다.
서버 실행과 별개이며 PC의 네트워크 프로필이 Private일 때만 아래 규칙이 적용됩니다.
이 저장소를 수정하는 것만으로 방화벽은 바뀌지 않습니다.

관리자 PowerShell에서 규칙이 없을 때 생성:
```powershell
New-NetFirewallRule -DisplayName "QRAlert FastAPI 8000" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 -Profile Private -RemoteAddress LocalSubnet
```
사진의 Set 명령은 이미 생성된 규칙을 수정하는 명령입니다:
```powershell
Set-NetFirewallRule -DisplayName "QRAlert FastAPI 8000" -Profile Private -RemoteAddress LocalSubnet
```
LocalSubnet은 로컬 서브넷 범위이며 특정 휴대폰 한 대만 뜻하지 않습니다.
휴대폰 브라우저에서 http://PC_IP:8000/health 로 먼저 확인하고 Expo를 연결하세요.
종료 시 서버 Ctrl+C, 개발용 규칙 제거:
```powershell
Remove-NetFirewallRule -DisplayName "QRAlert FastAPI 8000"
```
실제 서비스는 HTTPS 서버에 배포하고 앱의 API URL을 바꿉니다.

## NOVA AI / BAZE 키 설정
백엔드 루트 .env의 BAZE_API_KEY에 키를 저장합니다.
.env.example은 키가 없는 팀 공유용 양식입니다. .env는 Git 제외 대상입니다.
키를 교체한 뒤에는 서버를 재시작하세요. Expo에는 이 키를 넣지 않습니다.

BAZE_BASE_URL은 키를 발급한 배포의 Gateway 주소여야 합니다.
현재 기본값은 공식 설정 문서의 https://factchat-cloud.mindlogic.ai/v1/gateway 입니다.
BAZE_MODEL은 사용 가능한 모델 목록에서 고른 ID를 넣습니다.
키/모델 목록 확인:
```powershell
.\.venv\Scripts\python.exe -m scripts.check_baze
```
이 명령은 모델 목록만 조회하고 AI 텍스트 생성은 요청하지 않습니다.
401은 키가 유효하지 않거나 다른 BAZE 배포에서 발급된 경우입니다.
API 호출 시 크레딧은 키를 생성한 계정에서 차감됩니다.

현재는 키 저장, 인증 확인과 분석 결과 AI 설명 생성을 연결했습니다.
POST /api/analyze는 기본적으로 AI 설명을 생성합니다. include_ai: false를 보내면 AI 없이 규칙 기반 설명을 반환합니다.
코딩 에이전트 자체의 모델 제공자 변경은 별도 설정입니다.
참고: https://docs.mindlogic.ai/agent-setup/prompt.md

### AI 설명 응답과 비용 절약
- ai_explanation: 한국어 설명. AI 미사용/실패 시 규칙 기반 설명입니다.
- ai_status: generated(생성), cached(캐시), disabled(요청에서 끔), unavailable(실패/설정 누락), skipped(차단 대상).
- ai_model: 실제 AI 설명을 생성한 모델. 규칙 기반 설명이면 null.
- AI는 score/level/reasons/접속 정책을 변경하지 않습니다. 기존 warning도 함께 표시하세요.
- 모델에는 점수/등급/이유/검사 상태만 전달합니다. URL, IP, 쿼리, 브랜드 문자는 보내지 않습니다.
- 시스템 지침은 2~3문장을 요청합니다. 출력 예산은 512토큰이고 GPT 모델에는 reasoning_effort=low를 보냅니다.
- 전체 AI 호출 제한은 12초. 빈 응답, 잘린 응답, 4xx/5xx/timeout은 규칙 기반 설명으로 대체하고 유료 자동 재시도는 하지 않습니다.
- 동일 설정/요약은 10분 캐시(프로세스당 최대 128개). 여러 서버의 공유 캐시나 동시 중복 요청 병합은 아직 없습니다.
- 코딩 도구용 모델 설정과 독립적이며 BAZE_MODEL을 사용합니다. 설정 변경 후 서버를 재시작하세요.

요청 예시:
```json
{"qr_text":"https://example.com","brand_texts":[],"include_ai":true}
```


## 국가 DB 연결 확인
프로젝트의 data/GeoLite2-Country.mmdb 파일을 사용합니다.
.env에는 GEOIP_DB_PATH=./data/GeoLite2-Country.mmdb 를 지정하세요.
상대 경로는 현재 터미널 위치와 관계없이 백엔드 저장소 루트를 기준으로 해석됩니다.
DB/키는 Git에 포함되지 않으므로 팀원과 배포 서버는 각각 준비해야 합니다.
실제 DB 조회만 확인(AI 호출/외부 네트워크 요청 없음):
```powershell
.\.venv\Scripts\python.exe -m scripts.check_geoip
```
evidence.geoip.countries[].country_code는 국가 코드,
is_overseas는 한국(KR) 외 국가 여부이며 알 수 없거나 IP별 결과가 섞이면 null입니다.
국가 DB 갱신 시각은 database_updated_at으로 반환합니다.
evidence.tls는 인증서 만료 시각(ISO 8601), 남은 일수, 발급자, TLS 버전을 반환합니다.
DNS의 첫 번째 공인 IP에서만 TLS를 검증하므로 모든 CDN 노드를 검증한 결과는 아닙니다.
IP 주소형 URL의 RDAP은 not_applicable입니다.
RDAP 조회에는 IANA bootstrap을 프로세스별 1시간 캐시하며 RDAP 서비스 리디렉션은 추적하지 않습니다.
API 문서의 Evidence 하위 모델에 각 필드가 표시됩니다.
프론트는 level/score/reasons/ai_explanation을 표시하고
geoip.is_overseas는 국가 정보로만 표시하세요. 자동 접속하지 않습니다.
brand_texts는 2번 담당 비교 기능이 연결되기 전까지 분석에 반영되지 않습니다.
QR/이미지 판독과 사용자 확인 후 이동은 별도 Expo 저장소의 담당 범위입니다.
GeoLite 데이터의 출처: MaxMind, https://www.maxmind.com .
실제 서비스 배포 시 최신 데이터 유지 및 GeoLite 이용/출처 표시 조건을 확인하세요.

## 선택적 페이지 내용 분석
요청에 inspect_page: true를 명시해야 대상 페이지에 GET 요청을 보냅니다.
include_ai: false이면 HTML의 규칙 분석만 수행하고 AI를 호출하지 않습니다.

```json
{"qr_text":"https://example.com","brand_texts":[],"include_ai":true,"inspect_page":true}
```

동작: 기존 도메인/TLS/IP 검사 → 제한된 HTML 수집 → 폼/텍스트/설치 링크 분석 → BAZE 내용 분석.
AI 페이지 설명을 최상위 ai_explanation에도 재사용하므로 설명용 AI 호출은 추가로 발생하지 않습니다.
AI는 전달받은 본문 일부를 분석하며 브라우저나 도구를 직접 제어하지 않습니다.
본문 최대 4,000자를 외부 BAZE 모델로 전달합니다. URL·이메일·긴 숫자열은 제거하지만
본문의 모든 개인정보를 완벽하게 제거하는 기능은 아니므로 앱에서 사용자가 선택하도록 하세요.

수집 제한:
- 매 이동마다 HTTP(S), 80/443 포트, 자격증명 없는 URL, DNS 전체 공인 IP 여부 검사.
- DNS 재해석 없이 검증한 IP에 연결. 원래 hostname으로 Host/SNI/인증서 검증.
- 쿠키·사용자 인증 헤더·환경 프록시 미사용. BAZE 키는 대상 사이트에 전송하지 않음.
- HTTP 리디렉션 최대 3회, HTTPS→HTTP 이동 차단, 전체 수집 18초 제한.
- HTML 최대 256KiB. 첨부/비 HTML/압축 응답은 본문을 읽지 않고 중단.
- 알려진 실행/문서/압축/이미지 파일 경로는 요청하지 않음.
- JavaScript/iframe 실행, 하위 리소스 요청, 폼 제출, 파일 실행 없음.
- HTML/JS 기반 이동은 추적하지 않으며 meta refresh 발견 시 미완료 표시.
- 원문 HTML/본문은 응답/디스크에 저장하지 않음. 짧은 AI 결과는 프로세스별 10분 캐시.

page 응답:
- status/reason: 수집 성공 또는 차단/누락 사유
- final_url/redirect_chain: 확인한 이동 경로 (프론트에서 자동 접속 금지)
- final_evidence: 호스트가 바뀐 경우 최종 호스트의 RDAP/TLS/국가 정보
- findings: 서버가 관찰한 신호와 고정 점수
- ai_assessment: suspicious / no_obvious_signals / inconclusive
- ai_status/ai_explanation: AI 처리 상태와 설명
- coverage: 정적 HTML 검사 범위. no_obvious_signals도 안전 보증이 아닙니다.

추가 점수:
- 비밀번호 입력란만 존재: 0 (정상 로그인도 존재)
- 비밀번호 폼이 다른 호스트로 전송: 25
- 비밀번호 폼이 HTTP로 전송: 20
- 비밀번호 요구와 긴급/계정 정지 문구 동시 존재: 15
- 페이지 내 실행·설치 파일 링크: 35
- 최종 호스트의 기존 위험 신호도 합치되 동일 코드 점수는 중복하지 않음
AI는 모든 관찰 코드를 누락 없이 반환해야 하며 신호나 점수를 임의로 추가/삭제할 수 없습니다.
페이지 지시문은 비신뢰 데이터로 구분하고 구조화된 AI 응답을 검증합니다.
공식 도메인 DB와 브랜드 대조, 알려진 악성 URL DB, 동적 스크립트 분석은 포함하지 않습니다.

제한된 HTTP 수집기이며 별도 VM/컨테이너 샌드박스나 백신이 아닙니다.
공개 배포 전 수집 워커의 네트워크 송신 제한과 API 인증/요청 제한을 적용하세요.
설계 참고: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html

## 테스트
```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
네트워크에 의존하지 않는 입력·내부 IP 차단·위험 점수·API 계약 테스트.
실제 RDAP/TLS/GeoIP 통합 결과는 네트워크와 DB 준비 후 /docs에서 별도 확인하세요.
프론트 수동 검증: 정상 QR, QR이 아닌 이미지, 비 URL 문자열, 단축 URL,
실행 파일 경로, 스캔 후 자동 이동 없음, 사용자 확인 취소, 통신 실패.
이미지 판독/자동 이동 여부는 프론트 구현 후 해당 저장소에서 검증해야 합니다.

참고:
- https://www.iana.org/help/rdap-requirements
- https://fastapi.tiangolo.com/tutorial/cors/
- https://docs.expo.dev/guides/environment-variables/
- https://learn.microsoft.com/en-us/powershell/module/netsecurity/new-netfirewallrule
