# TEAM_15_BE

## 실행 (Windows PowerShell)

```powershell
cd C:\QRALERT\WOOWANGTHON_TEAM_15_BE
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

- 상태 확인: `GET http://127.0.0.1:8000/health`
- API 문서: `http://127.0.0.1:8000/docs`
- 분석 요청: `POST /api/analyze`

요청 예시:

```json
{"qr_text": "https://example.com", "brand_texts": ["브랜드명"]}
```

현재 분석 API는 요청 모델을 검증하고 아래 고정 응답을 반환합니다.
QR 텍스트의 주소를 열거나 외부 요청을 보내지 않습니다.

```json
{"status": "not_implemented", "message": "분석 기능은 아직 구현되지 않았습니다."}
```

`qr_text`와 `brand_texts`는 필수이며, 빈 `qr_text`는 허용하지 않습니다.
`brand_texts`는 빈 목록도 허용합니다. 잘못된 요청 형식은 HTTP 422를 반환합니다.
