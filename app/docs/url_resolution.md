# 단축 링크 해제와 2번 URL 검사

단축 링크는 암호를 해독하는 것이 아니라 서버가 반환하는 HTTP Location 이동 주소를 확인합니다.
AI는 필요하지 않습니다. 휴대폰이 대상 사이트를 열지 않고 백엔드가 요청합니다.

## 요청

POST /api/url/analyze:

```json
{
  "qr_text": "https://bit.ly/사용자가받은링크",
  "brand_texts": ["네이버"],
  "resolve_redirects": true
}
```

기존 brand_texts, store_id를 그대로 사용할 수 있습니다.
resolve_redirects 기본값은 false이며, 생략하면 기존과 동일하게 DNS·대상 사이트·AI 요청 없이 로컬 URL 검사만 합니다.

## 응답과 연결

기존 최상위 url_info / risk_signals 등은 스캔한 원래 주소의 검사 결과입니다.
옵션을 켜면 다음 항목을 추가합니다.

```json
{
  "url_resolution": {
    "status": "ok",
    "final_url": "https://m.naver.com/event",
    "redirect_chain": [
      {"url": "https://bit.ly/예시", "http_status": 302},
      {"url": "https://m.naver.com/event", "http_status": 200}
    ],
    "body_inspected": false,
    "auto_open": false,
    "requires_confirmation": true,
    "scope": "http_redirects_only"
  },
  "final_url_analysis": {
    "brand_domain": {"status": "matched", "brand": "네이버"},
    "risk_signals": {"brand_domain_status": "matched"}
  }
}
```

위 응답은 일부 필드만 보인 예시입니다.
final_url_analysis에 동일한 2번 URL 패턴·브랜드·매장 비교를 실행한 결과가 들어갑니다.
원래 단축 주소를 덮어쓰지 않습니다. 해제 성공은 사이트 안전을 뜻하지 않습니다.
이 API는 2번의 검사 결과를 반환하며 종합 위험 점수를 새로 계산하지 않습니다.
기존 POST /api/analyze의 inspect_page=true 흐름은 리디렉션 뒤 주소도 검사해 종합 판정에 반영합니다.
이번에는 최종 주소가 APK 등 파일 주소이거나 HTML 본문을 읽지 못한 경우에도 해당 주소의 2번 검사를 수행하도록 보완했습니다.

## 제한과 상태

- 301/302/303/307/308의 HTTP 리디렉션을 최대 3회 따라갑니다. 총 제한 시간은 18초입니다.
- 각 이동마다 공개 IP만 허용하고 DNS 검사 결과에 연결을 고정합니다.
- 내부·예약 IP, 사용자명/비밀번호 포함 주소, 지원하지 않는 포트·프로토콜, HTTPS에서 HTTP로의 이동을 차단합니다.
- 자동 리디렉션·쿠키·환경 프록시를 사용하지 않고 본문을 읽거나 실행하지 않습니다.
- 실행 파일 등 알려진 파일 경로는 요청하지 않고 관찰된 주소로 패턴 검사만 합니다.
- 자바스크립트, meta refresh, 로그인·쿠키·사용자 동작이 필요한 이동은 해제하지 않습니다.
- 단축 서비스가 접속을 막거나 서버·지역·기기에 따라 목적지가 달라지면 확인하지 못할 수 있습니다.

| status | 의미 |
| --- | --- |
| ok | 확인 가능한 HTTP 이동이 끝남. 안전 판정은 아님 |
| blocked | 연결 정책으로 차단됨. final_url_analysis를 만들지 않음 |
| unknown | 시간 초과·반복·횟수 초과·접근 거부 등으로 확인 미완료 |
| not_applicable | 파일 경로까지 확인 후 요청 중지. 그 경로의 추가 이동 여부는 확인하지 않음 |

unknown에는 확인한 주소가 있을 수 있지만 최종 검사 결과로 확정하지 않습니다.
실패를 안전으로 처리하거나 차단된 목적지로 자동 이동하면 안 됩니다.

## 테스트

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p test_url_resolution.py -v
```

모의 공개 응답으로 정상·상대 이동, 5가지 HTTP 상태, 파일 목적지, 내부 주소, 루프·횟수·시간 제한과 기존 API 호환성을 검증합니다.
실제 확인은 /docs에서 자신이 관리하는 공개 단축 링크로 실행하세요. 서버가 링크에 요청하므로 클릭 횟수·추적 로그에는 잡힐 수 있습니다.

참고: [HTTP 리디렉션 표준](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.4),
[aiohttp 요청 옵션](https://docs.aiohttp.org/en/stable/client_reference.html).
